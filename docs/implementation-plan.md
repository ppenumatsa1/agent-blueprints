# Phased implementation plan

## Approved observability and Workflow Studio follow-up in PR #62

**Approved; local UI checks passed, deployed telemetry privacy investigation
in progress, Azure verification pending.**
Reduce credential and fast successful polling noise while retaining errors,
slow requests, metrics, and connected API -> Foundry -> hosted MAF -> database
traces. Align the Order Resolution UI with the existing MAF Workflow
Studio reference and screenshot: history on the left, workflow/timeline in
the center, and approvals/evidence on the right, with a simpler responsive
layout. Keep the existing React, Vite, TypeScript, and CopilotKit dependency
choices unless an implemented feature demonstrably requires a change.

After both workstreams pass local checks and exact-head CI, prepare the next
existing-resource deployment and authenticated UI test using the repository
POC skill; do not execute either as part of this request. Keep self-approval
disabled, PR #62 draft, and the overall deployment plan **Approved / Not
Validated**. The seven Azure Policy audit findings, prior Foundry `403`, and
unavailable distinct reviewer remain disclosed, not waived. Acceptance
criteria and rollout boundaries are in the
[deployment plan](../.azure/deployment-plan.md#approved-pr-62-observability-and-operator-ui-correction).
Classify suspected privacy exposures from deployed configuration and
authorized synthetic tests; do not infer a live leak from local probes.
The hosted HTTPX request hooks now redact URL paths, queries, and userinfo in
local exporter checks while preserving parentage; deployed verification is
pending. Local baggage and exception canaries still appeared in OTLP payloads.

## Development POC execution priority

Repository guidance now prioritizes the smallest authorized end-to-end
synthetic cycle on the current CI-validated candidate before non-blocking
refinements. Existing explicit safeguards and honest reporting of unverified
checks remain required. Evidence: `.github/copilot-instructions.md` and draft
[PR #62](https://github.com/ppenumatsa1/agent-blueprints/pull/62). Next:
apply this priority to the pending Azure POC cycle without treating it as a
production-readiness claim.

## Single-identity synthetic POC in PR #62

Use the existing operator and PostgreSQL owner, not a new identity. Install
the optional protected grant/audit schema only on the dedicated POC database;
enable the generated hosted API and Agent A options only after verifying the
reviewed artifacts and actual scope, TLS, managed-identity principal mapping,
protected trigger ownership and operator grants. The owner command issues
the exact case/proposal/outcome grant after the native pause without storing
an Entra credential. Production remains default-off with distinct actors.
Local PostgreSQL fixture results do not prove Azure activation, hosted
continuation, adoption of independent provenance, or live multi-actor
authorization evidence. See the [operator runbook](../profiles/order-resolution/overlay/backend/poc/README.md).
The security review returned no verdict, so activation remains blocked.
Before any old-binary rollback, drain and account for all self-reviewed
cases, decisions, queued effects, grants, and hosted sessions. Historical
effect authorization accepts an already persisted self-approval without the
new protected-grant check; a clean journal alone cannot permit rollback.

## Explicit partial live acceptance in PR #62

**Selection implemented and locally verified; Azure execution pending.**
The live producer accepts an explicit `case_ids` list. It preserves default
all-nine behavior, source/deployment parity, and the ORS-005 fail-closed oracle.
Unselected canonical cases remain in the result as `status: not_run`, never
as normalized business success. Invalid or unsupported selection fails before
constructing a live client. ORS-009 requires distinct actors and is refused
when same-identity POC owner-database mode is configured.

Evidence: three isolated generated-backend selection/guard tests passed on
the change based on `28b7da3`. A generated API test reproduced HTTP 422 for
the old POC reviewer placeholder; six focused tests then passed for a stable
reserved UUID, operator-collision refusal, and a mocked five-case driver with
no grant or decision calls. The generated acceptance module passed 33 tests
and Ruff after an initial formatting failure was corrected. Next: verify the
integrated POC approval/rejection seam and execute an explicitly selected
live subset only when its deployment prerequisites are satisfied. All-nine
acceptance, native hosted recovery, deployment provenance, and production
authorization remain unverified or blocked; none is waived.

## Live acceptance oracle corrections in PR #62

**Locally verified; exact-head CI and Azure execution pending.** ORS-004 now
submits an identical pre-completion replay only after observing a nonterminal
case, verifies that replay is still nonterminal and uses the original case,
then compares the original and replayed terminal business outcomes. A fast
completion is explicitly unverified. ORS-008 checks each submitted record and
protected snapshot for the real `policy_evidence_invalid` failure, absent
proposal and decision, no recorded approval, action, claim or effect, and
exactly one terminal event. Missing or conflicting evidence stops the run.
Approval-request counts cover the application's durable local and hosted audit
events; they do not prove a global Foundry session or compute inventory.

Focused tests reproduced the prior false positives. A fresh independent
generation then passed 38 acceptance tests and three PostgreSQL-backed tests;
the isolated root suite passed 114 tests with two existing skips. The first
format check failed before the repository-specific formatting and lint checks
passed. Next: verify exact-head CI, then establish the actual scoped rollout,
in-flight-operation and provenance prerequisites before live testing. No
Azure outcome or production readiness is inferred from these local checks.

## Opt-in hosted image publication for PR #62

**Local implementation; integration and Azure verification pending.** Generated
projects can stage the deterministic hosted archive into a minimal image
context, build a non-root Python 3.13 Responses host, and opt into SDK
publication by immutable image digest. The image operation binds its journal
to the image and a fixed prior route; it checks that route before and after
creation, including ambiguous outcomes, during reconciliation and during
identity polling. It refuses ambiguous replay and checks the exact version's
configured image. The original source remote-build behavior remains the
default. These point-in-time control-plane checks are not atomic and do not
authenticate source-to-image provenance or measure the running container.

Local evidence at parent `28b7da3`: 17 publisher tests, eight instantiation
tests, 67 hosted tests inside the `linux/amd64` image, and the isolated root
suite (114 tests, two existing skips) passed. A synthetic, network-isolated
probe reached `/readiness` on port 8088. The default-PyPI image build failed
on a TLS handshake; the documented credentialless HTTPS mirror build passed.
An initial image failed host construction because its non-root home was
missing; the corrected image passed construction. The initial `/healthz`
probe timed out on a `404`. The readiness probe mocked prewarm and
observability; a separate unmocked, credentialless probe logged failed token
prewarm and telemetry initialization and does not establish live auth or
observability. The credential-free CI workflow now includes the publisher
regressions and a generated-image build with a mocked, network-isolated
composition check; exact-head CI is pending integration.

Next: transfer to the #62 owner for independent review and exact-head CI,
then coordinate the authorized registry push and fixed-route deployment.
Existing rollout gates are not weakened. Project pull permissions, a real
candidate version, session routing, hosted execution, and independent
provenance remain unverified. Route restoration alone is not a verified
binary rollback; see the POC rollback constraints above.

## Windows asynchronous PostgreSQL startup in PR #62

**Local acceptance passed; exact-head CI pending.** The default generated
backend discovery command reproduced two Psycopg Proactor `InterfaceError`s
and the related activity-stream 503 at `1d36ebf`. Native Python and AnyIO
`loop_factory` options now select Selector loops only for Windows asynchronous
PostgreSQL security tests, without changing the global policy or bypassing
cancellation, read-only, server-deadline or authorization assertions.
Windows Uvicorn development/debug startup uses its supported native
`--loop asyncio:SelectorEventLoop` option; other platforms keep their defaults.

Evidence: four focused checks passed, including real loopback Uvicorn
authorized activity and unauthorized-reader denial; ordinary
`python -m unittest discover -s tests -v` passed 176 generated base tests
and 273 profile tests with one existing real-provider skip. The original
three-case failure remains recorded, as do Psycopg connection ResourceWarnings.
The isolated root suite ran 114 tests with two existing adapter-selection
skips; generated backend lint and format checks passed.
This does not make existing embedded Proactor loops compatible, lift Windows
Selector socket/subprocess restrictions, or establish production capacity.

Next: publish and verify exact-head CI on the existing draft
[#62](https://github.com/ppenumatsa1/agent-blueprints/pull/62).
No Azure, firewall, provenance or recovery gate is changed.

## Hosted failure and acceptance review in PR #62

**In progress; deployment remains blocked.** Immediate failed Responses
start/resume outcomes, the case failure marker and the audit event are
transactional. Existing failures are preserved; delayed pending/action
callbacks cannot hide the failure before hosted completion, and new hosted
decisions are denied when a failed operation is recorded. No failed business
outcome, framework checkpoint, or replay is fabricated. A pending case with
any failure code does not offer approval in the UI.

The live adapter polls bounded reads for a hosted decision handle and for the
requested terminal state with a cancellable 60-second overall timeout,
rejects a different case or invalid channel, and does not repeat a decision
POST. Failed nonterminal cases continue refreshing while approval remains
hidden. The failure runner requires each passed case's successful correlation
to match the server-recorded request ID of its acknowledged start claim;
replays and legacy claims without that ID cannot cover it. This structural
claim correlation does not prove outbound dispatch or independently
authenticate producer metadata. Independent telemetry and provenance remain
mandatory. The full nine-case live result producer fails before submissions
because its ORS-005 native continuation is not verified. Hosted interruption
and reconciliation remain blocked.

Acceptance evidence on the follow-up candidate above `174eca3`: three
generated local happy paths; nine synthetic canonical scenarios; 42 focused
checks; 175 base and 272 profile backend tests under Windows Selector policy,
with one profile real-provider skip; 67 hosted-agent tests; 62 base and 67 profile frontend
tests plus builds/CSP; and Chromium local/history/studio suites of 1/5/1 for
each generated frontend. Three real Docker isolation tests passed using the
previously verified package mirror, including approval, rejection, and
capability-denial probes. A loopback HTTPS stalled-body probe timed out and
observed client socket closure. The isolated root suite passed 114 tests with two
adapter-selection skips. A pre-fix failure-state regression, the earlier
wrong-directory and missing-database scenario invocations, dependency setup
errors, two broad-UI fixture failures in each frontend, a profile studio-title
failure, a negative-test message assertion and a formatting check are retained
as failed attempts, not relabeled. A fresh Docker build using the default
PyPI index failed before tests on a package-download TLS handshake; the
mirror-backed Docker pass is a separate run. An additional root-level Ruff invocation
did not apply the generated project's path-relative adapter ignores; lint and
format checks pass from both generated backend directories. A shorter first
HTTPS probe did not establish that its server handler was reached and remains
inconclusive. The earlier default-Proactor backend failure remains recorded;
the scoped startup correction above does not relabel the original run. Historical
[run 45487881616](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45487881616)
passed at exact head `8c2a8c909b27b23802b4ee71450e82a5ebfcd2e7`, not this
candidate; [run 45496167774](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45496167774)
passed at `174eca3d9a6b02f5fe4d42f3e2ae4a360639d5c8`, before these changes.

Next: bind the reviewed commit to exact-head CI, then establish independently
administered build provenance and a fresh deployment observer. Verify a
firewall-preserving path for migration
`0004_order_resolution_hosted_response_outcomes.sql` and
`0005_order_resolution_hosted_start_claim.sql` before any authorized rollout.
No current-head Azure, live Entra, authenticated-browser, real
provider or Foundry recovery result is claimed.

## Advisory deployment-provenance preflight

**In progress; deployment provenance and rollout remain blocked.** The
independently copied [preflight](../blueprints/maf/workflow/docs/build-attestations.md)
uses GitHub CLI to verify three exact OCI build attestations against an
externally supplied policy. Certificate, numeric source IDs, event revision and
ref, pinned signer, GitHub-hosted runner, standard GitHub Actions SLSA
predicate, invocation and exact name/digest must agree in one verified result.
Malformed, duplicate, mismatched and ambiguous input fails closed; the result
always disclaims deployment provenance and release authorization. Local unit
tests exercise the three-role flow and negative mutations. A real public OCI
attestation passed with `gh` 2.103.3 and failed with a wrong source repository
ID; this does not verify a target artifact.

An external path is not proof of independently controlled policy or trusted
execution. A separately governed builder must bind the event SHA to the actual
reviewed checkout and all generated build inputs and derive each digest from
its own output. A separately governed observer must bind fresh authenticated
deployment identity, image, route, target, time and nonce to those subjects
under controlled deployment concurrency. Current ACA local-context builds,
Foundry `remote_build`, target attestations, observer, and protected environment
do not establish those guarantees. The pre-OIDC hard stop remains unchanged.
Next: obtain these independently controlled trust decisions and target evidence,
then separately validate any deployment; do not mutate Azure or the firewall as
part of this preflight.

## Hosted interruption evidence

**Blocked.** The previous live adapter cleared in-memory interrupted/unknown
markers and read the case without proving native continuation or authoritative
reconciliation. The hosted-interruption runner now blocks before any adapter
operation, and the live adapter refuses interruption and reconciliation
without clearing markers. Timeout/reconciliation scenarios using that adapter
therefore also remain blocked. Synthetic unit tests check these fail-closed
behaviors; they are not live recovery evidence. Next: establish independently
verifiable native continuation and durable outcome evidence before enabling
the scenarios. No Azure operations or live tests were performed.

## Live acceptance credential boundary

An independent review identified bearer disclosure on redirects and unrestricted
browser session-storage injection. The acceptance client now requires a
separately configured matching HTTPS origin and refuses all redirects; the
browser limits injected storage to that origin and rejects cross-origin state
and all cookies. The model evaluator requires its own independently authorized
HTTPS origin and also refuses redirects. Focused checks use synthetic tokens and
routed browser pages; the independently generated profile is checked without
live Azure or Entra access. Existing local browser suites remain intact. CI
and real deployment configuration remain unverified. Next: review exact-head
CI and independently authorize the live origin. This does not establish
trusted deployment provenance, proxy safety or isolation for same-identity
approval.
The same trace found a hosted Responses POST using default redirect handling
and browser API/stream fetches that followed redirects. Both now reject
redirects; the hosted client records an ambiguous outcome as unknown. Synthetic
loopback and transport checks do not prove live service or proxy behavior.

## Hosted approval UI repair in PR #62

**In progress**, based on `19e1837e2cb4d0781aa34ec7e345c5fed30b7a03`.
Acceptance: local and hosted decisions carry the server-selected channel;
asynchronous case changes become visible without stale case replacement or
retaining a case after read authorization is revoked. Timed-out or transient
refreshes retry while authorization failures stop and clear the case; sign-out
discards the prior workspace. Source frontend tests passed 59; independently
generated profile tests passed 64, with build, CSP and three Chromium origin
checks. The isolated repository suite passed 114 tests with two
adapter-selection skips. A generated profile passed local automatic and
human-approval API/MAF/PostgreSQL happy paths and Agent A loopback composition
using synthetic identities and a Foundry fixture. These are not proof of
actual Foundry execution.

The default Windows Proactor full generated-backend run failed three of 251
tests (two Psycopg async errors and a stream 503 instead of 200); one
real-provider test was skipped. A separate Windows Selector-policy run
completed 251 tests with the same real-provider skip, and all nine canonical
scenario cases passed independently through the generated local adapter.
Do not relabel the Proactor failure.

The generated profile's signed-out Chromium check initially failed at
`1591e20293bbfad351f54243f74fb471203bc274` because it inherited the base
title expectation. A profile-specific title expectation passed locally, as
did the unchanged base check; CI now runs the check on both generated
frontends. Next: review exact-head CI and, after trust and isolation are
established, separately run authorized live approval, rejection,
checkpoint/resume, restart, idempotency and recovery checks.

## Acceptance harness contract repairs in PR #62

**In progress**, starting at `19e1837e2cb4d0781aa34ec7e345c5fed30b7a03`.
Acceptance criteria: load the profile adapter using the runner's target and
workflow environment contract; associate actual HTTP correlations with each
passed case without treating an approval handle as a correlation ID; and
select the generated UI's real controls. Source runner and independently
generated backend and UI fixture tests pass, as does the generated frontend
build. These checks do not verify a hosted recovery, human identity, effect,
deployment provenance or a live browser session.

The recovery-evidence and credential-safety changes are integrated in
[draft #62](https://github.com/ppenumatsa1/agent-blueprints/pull/62). Next:
review exact-head checks. Keep failure injection blocked by the existing
provenance hard stop; no Azure call or live evidence is claimed.

## Fixed offline synthetic manual tests above PR #61

**In progress; local implementation and validation completed, draft/CI review
pending.** Base verified against open draft #61 at
`a78854c5fff4d4f518e9fea729d0bba0123ce2bb`.
The incremental deliverable is an operator-triggered fixed runner rather
than unsafe browser dispatch. It packages the canonical native MAF approval
graph plus fixed in-memory synthetic state in a separate image. It accepts
only approval/rejection selection (and a credential-free HTTPS package mirror
for builds), with no code/image/payload/factory injection. Actual pre-start
Docker inspection enforces network none, read-only root, unprivileged user,
no capabilities or privilege escalation, no user mounts/devices/ports,
credential environment exclusion and resource limits. Runtime negative
network/metadata and filesystem probes must pass before the native graph.
The host, daemon, reviewed sources and dependencies remain trusted.

Acceptance/evidence: eight boundary unit tests pass; three real Docker tests
pass in each of source, independently generated base and generated profile,
including both native decisions and six actual altered-container denials
before execution. Both generated operator CLIs pass independently. Isolated
repository suite: 114 tests with two inherited adapter-selection skips; Ruff
0.14.13 lint/format and whitespace checks pass. Local package-download TLS
failure was resolved with an HTTPS public mirror without changing dependency
hashes or disabling TLS. CI adds source and independently built base/profile
Docker checks with the original checkout temporarily unavailable; exact-head
CI remains pending.

No application business workflow/action, human approval, model, database,
checkpoint, durable recovery, browser integration, same-identity exception or
atomic exception audit is implemented or claimed by this layer. Production
controls remain unchanged. Builds use public registries and mutable base
tags; source-to-image attestation and arbitrary hostile-code sandboxing are
not claimed. Next: review the stacked draft and exact-head CI without merging
or changing stack metadata, Azure resources or firewall rules. The
[operator guide](../blueprints/maf/workflow/docs/offline-synthetic-tests.md)
records runnable commands, assumptions and limits.

## Polling fallback containment above PR #60

**In progress**, based on `99b4303a209c983ca7d306fd6d23473476e85ff6`.
The case, activity and history GET handlers share a per-PostgreSQL-store
nonblocking admission limit. At the supported minimum pool size of two, one
read is admitted for compatibility. This does not leave two business
connections: a disposable PostgreSQL reproduction of one simulated stalled
read caused a local workflow submission to time out while trying to borrow its
nested connection. Configure at least three connections for a polling limit
of `min(4, pool_max_size - 2)` and two slots outside polling. Other traffic
can still use those slots. A saturated handler returns 503 after
authentication. Slots are released only after the actual synchronous handler
exits, not when an asynchronous caller cancels. Tests reproduce
pre-containment exhaustion and cover repeated stalls, rejection, cleanup and
generated Order Resolution against disposable local PostgreSQL 17.12. The
minimum-size correction passes six focused source tests, six in an independent
generated base and nine in an independent generated profile; both generated
Ruff checks pass. On the preceding head, full source and independent base
suites passed 168 each and the independent profile passed 235 with one
real-provider opt-in skip using the Windows selector event loop; instantiation
tests passed 8/8. Default Windows Proactor runs failed
in all three suites with two Psycopg async errors and one stream assertion
failure each; selector reruns do not erase those failures. Exact-head CI
remains pending.

This is not a network timeout, thread termination or exclusive business-pool
reservation. Other traffic may still exhaust the pool, authentication is
outside admission, and custom implementations may borrow more connections or
spawn work. Managed-identity acquisition, network black holes, shutdown and
deployment-wide capacity are unverified. Next: review the draft and exact-head
CI, then separately address these production reliability limitations.

## Remediation above PR #54

**In progress**, starting at
`11b4bb04c92626fddc3a50b135a8a6d0e379d52a`. Validate fixes independently
and on the exact draft-PR head; do not infer production readiness from local
checks. Broad public PostgreSQL firewall access remains a **HIGH production
blocker** ([#56](https://github.com/ppenumatsa1/agent-blueprints/issues/56)).
Firewall mutation is not authorized. Deployment and live acceptance are
conditional on exact-head tests and verified safe target, isolation,
permissions, and immutable provenance.

The requested same-identity exception is **blocked**, not implemented: the
synthetic adapter uses configured PostgreSQL and the runtime cannot verify
storage, credential, permission, and network isolation or trusted deployment
provenance. Production separation of duties remains enforced, including at
the effect boundary. A separately verified isolated environment and atomic
exception audit would be prerequisites; a flag is insufficient. The studio
does not execute application-supplied manual-test callbacks in any environment.
This interim control does not fulfill isolated synthetic test execution. An
audited fixed in-process test path, without arbitrary callbacks, would still
need proof that its dependencies and permitted operations cannot reach real
business effects; general browser or application code is not sandboxed.
Such a path could test pure transformations over bundled synthetic fixtures,
without persistence, network calls, or client access. It would only cover that
audited code under a trusted build/runtime, not the real workflow, a general
sandbox, or release evidence.
The successor starts from verified cloud head
`766d8e46c13447deb10a9a1903e12af296163818`, independently of the interrupted
cloud session. SSE no longer submits synchronous work to an executor or
borrows API-pool connections. Four cancellable async operations and 32 streams
are allowed per process. Malformed token headers fail before I/O. A five-minute
per-application signing-key cache with single-flight fetch and 30-second
unknown-key/failure refresh throttling addresses the independent review's
repeated-JWKS-fetch finding; expired keys never serve as a failure fallback.
Async HTTPS key retrieval and separate read-only
PostgreSQL connections have five-second I/O/statement/lock deadlines. Unsupported
custom service/store/policy/identity implementations and managed-identity
database credentials fall back to independently authorized polling. Regression
tests cover actual locked-query cancellation, connection cleanup, HTTP cleanup,
capacity recovery, token expiry, policy revocation, and server read-only/deadline
enforcement. DNS may still use library executor threads; resolver shutdown and
TLS/network-black-hole behavior are not verified. Polling remains synchronous;
the successor containment and limitations are recorded above. I/O deadlines
remain a reliability blocker; this is not full I/O resilience.

Successor local validation on 2026-11-24 uses complete backend discovery, not
the former curated module list. Source and independent generated base backend:
**162 tests each, no skips**. Independent generated profile backend:
**228 tests, one real-provider opt-in skip**, with the generated Agent A source
explicitly selected and the PostgreSQL/HTTP loopback executed. Complete
generated Agent A suite: **63 tests, no skips**, after installing its pinned
requirements. Independent generated base verification: **52 tests, no skips**;
profile canonical contract: **9 tests, no skips**. The isolated repository suite
runs **105 tests, two adapter-not-selected skips**. Frontend suites:
source/base **54 each**, profile **56**, with builds and CSP checks passing.
Offline Chromium local/history/studio suites pass **1 + 5 + 1 tests** in both
source and independent generated base. The optional-adapters spec now covers
evidence projection failure and normal approval as well as disabled callbacks;
it does not claim restored isolated manual execution. Protected `local.spec.ts`
and `live.spec.ts` are unchanged. No live browser spec was executed.

Locked Ruff 0.14.13 formatting is checked against the generated backend's
100-column configuration, including the profile observability source. CI now
uses full source/base discovery and all three offline generated browser suites.
The independent read-only follow-up found no actionable issue in the cache
correction; it retained the disclosed DNS/network/shutdown and polling
limitations. Builds retain the >500 kB chunk warning; backend fixture runs emit non-fatal
open synchronous-connection ResourceWarnings. These are not production
readiness evidence. Exact-head CI is tracked on the successor draft PR.
[Historical CI run 45309564583](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45309564583)
at `b7004af4316a419f7b5afd0048a388e9c2af9705` failed generated-profile
formatting before executing its profile tests; six jobs passed. That failure
is not relabeled by successor checks. The hosted failure runner now
preserves validated HTTP status and hosted correlation fields for the existing
App Insights verifier; no live telemetry has been checked. The lost-ack test
supplies a remote ID rather than verifying an operational reconciliation source.
Acceptance fault controls default off and require an operator role and exact
revision, but lack an enforced non-production environment boundary.

Next: inspect exact-head CI and independent review, retain both drafts, and
resolve the disclosed polling/network and isolation blockers separately. Do
not deploy, merge, or infer an operational self-approval path.

The manual cloud-validation workflow now checks both evidence-run heads and
success states, requires the configured trusted deployment workflow path,
checks the exact active-revision artifact, and defaults destructive injection
off. The active-revision JSON and hosted inspection are not signed source-to-
image attestations, so the failure-injection job hard-stops before Azure login
or adapter execution. No workflow in this checkout currently produces the
required deployment evidence artifact, so that producer path remains unset and
exact deployment provenance is blocked. The job is isolated behind the dedicated
`azure-foundry-failure-injection-nonproduction` GitHub environment, checks the
exact configured Container App resource ID and
synthetic environment marker, installs locked dependencies and pinned `azd`
before Azure login, verifies the OIDC-selected tenant/subscription, and removes
the adapter authentication file on every outcome. The generated harness also
requires the adapter to identify the same synthetic target and exact source
and deployment revisions. Existing firewall rules are not read or mutated by
this workflow.

These are fail-closed code contracts, not proof of isolation. The protected
GitHub environment and required reviewers, its OIDC federated credential,
resource-scoped Azure role assignments, exact target variables, adapter auth
material, and a reviewed compatible adapter are tenant/repository settings
that are not present or verifiable in this checkout. Azure CLI destructive
operations are therefore not yet safe to dispatch; no Azure deployment,
restart, session stop, fault injection, firewall change, or live acceptance
was performed. Preserve issue #56 and its existing firewall rule. Resolve
those authorization and environment prerequisites before any live run; this
change does not populate tenant values or claim rollout readiness.

## UX stack Layer 5: read-only protocol context

**In progress; stacked on PR #53** at
`3bdf2646095383583445e0cea04d34d0658c694f`. A selected,
already-authorized case can provide only its validated status through an
explicitly activated AG-UI context registration or CopilotKit v2 hook adapter.
The default has no optional protocol dependencies or automatic agent calls.
Neither integration supplies workflow mutations, agent runs, tools, event
streams, or transport. Adapter code is trusted and its cleanup cannot be
enforced. Configured consumers may transmit the status during later runs.
Focused unit/axe and browser checks, a production build, and a local
`@ag-ui/core@1.0.4` schema plus
`@copilotkit/react-core@2.0.0-rc.53` real-hook lifecycle check with a
synthetic consumer passed. This does not test a real provider or remote
agent. Independent generated-project checks and exact-head CI remain pending.
Next: verify those boundaries and retain draft status.

## UX stack Layer 4: optional evidence and synthetic tests

**In progress; stacked on PR #52** at
`f16a4f504f3a80f98819a8750058cabf6778559d`. Typed optional profile adapters
project explicitly allowlisted evidence as text from an already authorized
selected case. Manual-test callback execution is now disabled in all
environments: trusted application code is not sandboxed, and omitting a
workflow client or using a build flag cannot prevent real effects. Default
profiles disable both capabilities.
Adapter errors are surfaced without preventing
the normal workflow. Focused UI checks are available; generated-project,
browser and exact-head CI verification remain pending. Next: finish those
checks and retain draft status.

## UX stack Layer 3: authenticated live activity

**In progress; rebased on PR #51 head
`14a709e0f682db3776e92ed9cdc194369fecaf47`; draft CI pending.** A bounded
SSE channel emits privacy-safe refresh signals after token and per-case policy
revalidation. React uses bearer fetch and independently authorized activity
reads to reconcile whole snapshots, avoiding the false assumption that audit
IDs or timestamps follow commit order. A disconnect causes a fresh scan; a
valid refresh on a stream sustained for 20 seconds resets the renewal failure
budget; three short or failed streams fall back to ten-second polling. Token
acquisition is cancellable from this caller and bounded, though the underlying
MSAL operation is not cancelled. Scans start at most every 15 seconds and stop
at 50 pages or 60 seconds, displaying an explicit limit error. This is eventually reconciled activity, not
an exactly-once stream or a point-in-time snapshot under concurrent writes.

Rebased focused checks pass 33 UI tests, build and both history browser specs,
plus six stream-security tests and backend lint. Before rebase, isolated
PostgreSQL 17 CI-selected generated base/profile backend suites passed 128
and 177 tests (one profile opt-in skip), and generated UI suites passed 38 and
40 tests, builds and browser specs. The isolated repository suite passed 105
tests with two adapter-selection skips. Fresh generated and exact-head checks
remain pending. The inherited profile telemetry fixture mismatch is unchanged.
Timed-out synchronous identity/database workers cannot be cancelled by the
stream and may hold a pooled connection until they return; see the bounded
remediation and polling limitation above. Next action: finish verification
and do not merge or deploy.

## UX stack Layer 1: reusable workflow studio shell

**Implemented locally on a frontend-only branch stacked above draft PR #49;
exact-head CI remains pending.** Layer 1 introduces a generation-time
`WorkflowStudioProfile` boundary for generic titles, descriptions, labels,
capability flags, safe plain-text payload projections, optional React
rendering, and profile-owned decision binding. The base profile contains no
order, refund, shipment, or customer vocabulary. `StudioShell`,
`RequestComposer`, `CaseSummaryPanel`, `ApprovalPanel`, and
`CaseMetadataPanel` reuse the existing `WorkflowCase` and `WorkflowClient`;
the protected endpoints, delegated scopes, Entra/MSAL behavior,
server-authoritative record authorization, UUID validation, secure
idempotency-key reuse, approve/reject behavior, and visible recovery/failure
states are unchanged.

History, live activity, evidence, manual tests, AG-UI, and CopilotKit are
disabled capability flags only. Layer 1 does not add their runtime behavior
and makes no backend, API, database, Azure, RBAC, network, or firewall change.
The independently generated application owns the profile, components, tests,
and production browser configuration without importing `agent-blueprints` or
the reference repository. Existing PR #49 `local.spec.ts` and `live.spec.ts`
remain unchanged; a separate production-built signed-out studio-shell spec
was added.

Local evidence: 12 base Vitest/Testing Library tests including axe checks,
14 tests in a fresh independent Order Resolution generation, base and
generated production builds, CSP verification, the unchanged local Chromium
spec, the new production-build Chromium spec, and the focused independent
instantiation contract all pass. The required repository suite passes 105
tests with two documented application-adapter-selection skips. The existing
Vite chunk-size warning remains non-blocking and is not relabeled as a pass.
Next action: obtain exact-head CI on the stacked draft PR and keep later UX
layers separate.

## UX stack Layer 2: authorized history and activity

**Implemented locally; draft PR #51 is open and the authorization/pagination
correction is locally verified; exact-head CI passed.** This increment is a
distinct draft PR stacked directly above PR #50's
`ppenumatsa1-ux-layer-1-studio-shell` branch. It reuses the PostgreSQL
`wf_cases` owner/reviewer/tenant fields and committed `wf_audit` events; it
does not add a competing business-state store or inspect MAF checkpoint
contents. Case history uses bounded keyset pagination and optional status
filtering. Fixed SQL tenant/owner/reviewer predicates scope candidates; the
configured `AccessPolicy.authorize_read` is then applied to complete internal
records before public pagination is calculated. At most 1,000 candidates are
authorized per request over 10 batches of at most 100; if more candidates
remain before the authorized page is complete, the service returns a generic
503 without partial items or a cursor. Permitted records are not silently
dropped, and no application policy input is translated into SQL. Record
activity first follows
the configured case-read policy and repeats the same SQL authorization
predicate. Responses omit payloads, actor
identifiers, request/checkpoint identifiers, prompts, model output, and tool
content. Only explicitly mapped audit event names are returned; unknown and
Order Resolution-specific audit rows are not exposed by the generic endpoint.

The React profile supplies generic history/activity labels and event text. The
sidebar and timeline use the existing scoped HTTP client, validate the
versioned response shapes, and discard stale responses when the filter or
selected case changes. Existing `/api/cases/{id}` and decision behavior remain
unchanged. No migration is needed because the required generic tables and
columns already exist in the immutable baseline. No cloud changes, streaming,
evidence, manual-test, AG-UI, or CopilotKit work is included.

Local evidence for this correction: six focused PostgreSQL authorization/
privacy/status/cursor/event/budget tests and all 136 source backend tests pass. The
stricter-policy regression denies owner- and reviewer-accessible cases and
verifies that items, cursors, and empty-page metadata include only
policy-authorized records. A 1,001-candidate deny-all test verifies that the
1,000-candidate limit raises an explicit typed error; the API maps it to a
generic 503 with no partial page or cursor. An existing within-budget
regression verifies successful pagination across denied candidates. The
focused six-test PostgreSQL/security selection, full 136-test backend suite,
and isolated 105-test repository suite pass. Exact-head CI run
[45294440225](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45294440225)
passed all seven jobs on `bfcbe1e6ee31945942c45422799374ddb026aeb1`.
Frontend unit/axe tests pass (21), as do the production build, CSP check, and
the source history/studio production-browser specs. Deferred frontend tests
verify that new history-filter and activity-case generations clear stale
load-more state. The required isolated repository suite passes 105 tests with
two documented adapter-selection skips. Prior generated base/Order Resolution
verification suites passed 52 and 61 tests, and generated Order Resolution
hosted-agent tests passed 63; exact-head CI passed all generated validation.
PR #49's existing local/live E2E files remain unchanged byte-for-byte
against the parent. Vite continues to report a >500 kB bundle warning.

The generated Order Resolution backend suite ran 190 tests, with two explicit
skips (Agent A source opt-in and real-provider evaluation opt-in) and one
pre-existing unrelated failure:
`test_live_client_uses_response_correlation_id_for_telemetry_pair` expects a
telemetry projection without `http_status`, while the current client includes
it. The history/activity tests pass. Do not suppress or relabel this failure;
exact-head CI passed, and this local gap remains disclosed in the draft PR.
No Azure state, streaming, evidence, manual-test, AG-UI, or CopilotKit work is
included. **Next action:** obtain human review of PR #51; retain disclosure of
the inherited local generated Order Resolution test failure. Do not merge or
enable auto-merge.

## Local Azure/Foundry integration checkpoint

**Completed locally, validated, and partially provisioned for E2E.** The C -> A -> B -> D integration from
`886b628fdea02f9089c385b4ed0fc46d90f375e8` preserves native MAF checkpoints,
Foundry-managed hosted state, and API-owned PostgreSQL business persistence.
The [integration acceptance table](master-checklist.md#local-azurefoundry-integration-acceptance)
records exact owner heads, targeted and full-suite evidence, disclosed skips,
and remaining cloud/production limitations.

The final canonical image includes C's system-CA discovery correction and B's
no-deployment-override contract. Real PostgreSQL 17 verifies normal hosted
startup plus wrong-hostname and untrusted-CA refusal, without a trust bypass.
Fresh generated backend, hosted, verification, and canonical-image checks pass.
Read-only acceptance inspection found that PR #49 run `45099182951` passed all
seven jobs but its `maf-generated-evidence` artifact recorded default
pull-request merge revision
`0859bf2f98f775ae2910deb770375ddfc240330f`, not deployable source head
`a6ab0a1ac6412e17345e9d46c0b70fafe55faad3`. The corrected PR #49 head
`d516410f3c63472152b13f28f65081d4006ec04b` passed all seven jobs in run
`45152016819`; all 12 downloaded revision-bound evidence documents record that
exact head. The `maf-independent` evidence producer now explicitly checks out
the PR head before recording `SOURCE_REVISION`. The telemetry verifier also now resolves
the deployment-emitted Log Analytics ARM resource ID to the customer/workspace
query GUID instead of passing an unsupported ARM path to `az monitor
log-analytics query`. The cloud health verifier now also enforces exact
`/healthz` `204` and unauthenticated protected API `401` responses rather than
accepting broader success/authorization status sets. Live Azure preflight, subscription policy review,
provider validation, and provider-backed what-if passed with 21 creates and no
modifications or deletions, so `.azure/deployment-plan.md` is `Validated`.
The first corrected apply created the PostgreSQL server but exposed concurrent
Flexible Server child writes. The module now orders administrator, TLS
settings, database, and optional firewall resources; Bicep validation and all
17 infrastructure tests pass locally. Live database configuration then
verified Entra-only PostgreSQL 17, `verify-full` TLS 1.3, platform migration
revision `0001`, all ten Order Resolution tables, and the non-admin API UAMI
principal with DML/sequence privileges but no schema-create or elevated role
attributes. A Windows migration defect was corrected by delimiting
`${database}` in the URL and using the generated locked `certifi` CA bundle
for operator-side psycopg while preserving system trust in the Linux runtime.
The broad temporary rule `temporary-e2e-public-remove-after-e2e`
(`0.0.0.0`-`255.255.255.255`) must be removed after E2E and replaced by actual
API outbound addresses plus the current operator address if still needed.
The generated startup correction at
`2ef516107b47f57ea266021b2651ca13b235bd3e` and frontend upstream-TLS SNI
correction at `9d5a66315f223cb424b70a20679cd6d950f47ffb` are deployed as the
sole healthy API and web revisions. ACR runs `ch5` and `cha` produced immutable
digests; live checks prove API health `204`, unauthenticated protection `401`,
web root `200`, proxied web health `204`, and successful API-UAMI
`database.connect`. The API retains the active hosted identity/version binding,
and no business action was executed. Next: preserve exact deployment evidence,
complete only separately authorized hosted/browser/evaluation checks, and
restrict the firewall. These checks do not authorize merge, release, or
production-risk acceptance.

A subsequent observability deployment stopped before replacement after the
immutable API image failed during module import:
`order_resolution_hosted.client` required the newly app-owned
`order_resolution_hosted.credentials` sibling, while the independent-project
generator still copied only the historical two-file bridge set. The correction
uses one typed generator manifest for `bridge.py`, `client.py`, and
`credentials.py`, derives the transitive local relative-import closure from the
entry point, and fails generation if the manifest omits a dependency or adds an
unrelated hosted-runtime module. The generated-project contract, deployment
preflight contract, temporary composed-wire fixture, and in-image smoke now
share that package boundary. Local evidence is 17 focused source contracts,
164 independently generated PostgreSQL tests, and a successful normal
backend-only image import/composition regression. No Azure, Foundry, RBAC,
traffic, workflow, database, or firewall mutation is claimed. Resume deployment
only from a green exact-head run in a separately authorized phase.

## Hosted durability correction checkpoint

Two independently verified crash windows are corrected in source only. The
pending case transition, hosted binding, audit insertion, and decision-handle
binding now use one PostgreSQL transaction through a typed connection helper.
The replay branch locks and verifies the same proposal, and can repair a legacy
unbound pending proposal only when its request identity and channel match.
Separately, a fresh hosted Responses operation obtains its authorization token
before the durable claim. A pre-request token failure therefore creates no
claim and sends no POST; a later retry can submit exactly once. Lost-ack
ambiguity after a request may have crossed the boundary is unchanged.

Local evidence is two focused PostgreSQL regressions, 63 source hosted tests,
166 independently generated PostgreSQL/backend tests with one explicit
provider-opt-in skip, 63 generated hosted tests, nine canonical ORS contract
tests, 105 repository contract/readiness tests with two documented
adapter-selection skips, and passing Ruff checks. Next action: require all
exact-head PR jobs to pass, then consider a separately authorized immutable
deployment and focused live recovery rerun. Do not infer cloud acceptance from
these local tests.

## Immutable version-9 deployment and signal checkpoint

Exact source `a302e939810283bce47867b8fa088374f3d204ad` passed all seven PR
#49 jobs in
[run 45275635199](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45275635199).
The authorized immutable rollout then passed 32/32 deployment checks. Hosted
`order-resolution:9` is active with source and deployment revision
`a302e939...`; its archive SHA-256 is
`84a18cc7a233e252b06fcd869ac53a6c881e7355ab82a0957ec6c43b2992c595`
and publication digest is
`781e882933dc02a0edce61356a6502d430ce20e80ed0b39e60e17e5029f025e7`.
API revision `aborsfoundpv2n45-api--a302e939` receives 100 percent traffic
from image digest
`sha256:6991536d9cf23efd9bdf1b21a94d1c9bddaa245a151d4b709a13235905eebf79`.
The unchanged web revision `aborsfoundpv2n45-web--0000002` remains on
`sha256:f8a43d68c38707a61ab60b673401427d0c7266d1ebb3dde04a602c07bf3a9ce7`.
API health is `204`, unauthenticated protection is `401`, web root is `200`,
and web health is `204`. The API managed identity connected as
`aborsfoundpv2n45-api-id` to database `workflow` with
`sslmode=verify-full`, system trust, and TLS 1.3.

The bounded live signal comparison passed 16/16 checks using exactly two
synthetic cases. Case `169a5177-543c-4d06-ac61-314252a2c39f`, trace
`d4d3af124c8d4aee8b240bad2af0a78f`, completed with one synthetic
PostgreSQL effect and zero real or external effects. Case
`4b368d22-7335-4ac0-8917-9ee4f7cd63a1`, trace
`2c64659b9cbc467488d53e67e972b7fc`, remains durably pending HITL with
zero decisions, claims, effects, terminal events, or resume attempts.
Compared with version 7, total/API/hosted spans changed
`276/74/202 -> 243/26/217`; pooled-borrow `database.connect` spans changed
`52 -> 0`, MSI token spans `54 -> 52`, Foundry dependencies remained `128`,
and optional A365 startup exceptions changed `2 -> 0`. Physical database
open/create evidence, platform dependencies, graph integrity, HTTP result
semantics, exact version binding, and deterministic privacy-safe workflow
stages remained observable. Exporter failures, raw-content rows, and payload
markers were zero.

Retained machine-readable evidence is under
`deployment-observability-signal-a302e939/deployment-verification-summary.json`
and
`signal-comparison-a302e939-v9-20261123T222235Z/signal-comparison.json`
with its concise `signal-comparison-summary.json`.

Two next actions remain explicit. First, use a distinct delegated reviewer for
the pending HITL resume and durable trace-link proof; do not substitute a
workload identity or relax reviewer authorization. Second, defer PostgreSQL
firewall hardening until both API and operator/migration paths can be validated
without the broad rule. Read-only evidence currently records the broad rule,
five narrow Container Apps rules, 407 advertised outbound addresses, public
network access, and the repository's temporary exact-IP `deployment-operator`
path. No firewall/network mutation occurred. These results do not authorize
production, merge, or removal of PR #49's draft status.

## Phase 0: foundation

The [foundation PR](https://github.com/ppenumatsa1/agent-blueprints/pull/1)
established the architecture, reference analysis, catalog, engineering
standards, initial contracts, and GitHub-hosted validation under the MIT
License. The [follow-up](https://github.com/ppenumatsa1/agent-blueprints/pull/2)
added profile-aware contracts, the supplied architecture source, and the
[living checklist](master-checklist.md).

The [cross-framework Order Resolution specification
proposal](order-resolution-specification-proposal.md) adds a documentation-only
business contract for triage, policy retrieval, deterministic resolution,
authorized approval/rejection, idempotency, crash/restart recovery, and
evaluations. Its versioned synthetic set covers automatic completion, approval,
rejection, duplicate commands, worker recovery, policy-evidence failures, and
authorization denial. It requires framework-native workflow/checkpoint
providers and keeps PostgreSQL application persistence separate; it does not
add a runtime, custom checkpointer, compatibility shim, or Azure resource.

Merged [PR #42](https://github.com/ppenumatsa1/agent-blueprints/pull/42)
adds the [executable acceptance fixture](../scenarios/order-resolution/README.md),
versions that contract as `order-resolution-spec/0.1.0`, and encodes exactly
`ORS-001` through `ORS-009`. Root tests enforce the exact synthetic policies,
decimal USD round-half-up refund amounts, approval/action/outcome expectations,
and explicit policy-evidence failures. Normalized `business_outcome`
assertions remain separate from framework-specific `technical_execution`
assertions. This is contract encoding, not implementation or readiness
evidence. Parallel workstreams B, C, and D depend on this contract and must not
redefine its normalized facts or outcomes.

Merged [PR #44](https://github.com/ppenumatsa1/agent-blueprints/pull/44)
adds one explicit `order-resolution` generation profile to the existing safe
copy generator. Default generation remains unchanged. The generated project
owns its FastAPI/React/PostgreSQL/Compose application, deterministic policy
rules, database-only synthetic action, native MAF `Executor` and
`WorkflowBuilder`, host-selected file checkpoints, tests, locks, and copied
acceptance assets. A fresh external generation passed 117 inherited and
profile backend tests on PostgreSQL 17; those tests executed `ORS-001` as one
automatic `USD 7.90` action, `ORS-002` as a native pause followed by one
authorized `USD 18.50` action, and `ORS-006` as a persisted fail-closed case
with no checkpoint, decision, action claim, or effect. Generated frontend
tests/build/CSP checks and a standalone Compose root/health/auth boundary also
passed locally. These results are implementation evidence, not full nine-case,
hosted, remote-effect, evaluation, or production-readiness evidence.

Merged [PR #41](https://github.com/ppenumatsa1/agent-blueprints/pull/41)
integrates application-owned PostgreSQL requests, proposals, atomic decisions,
effects, audit records, synthetic downstream reconciliation, and an explicit
profile migration into that generated application. Effect identity includes
case, proposal version, action, and destination. Process tests cover termination
around decision persistence and effect send; timeout-after-send remains unknown
until authoritative observation. The generated runtime adapter executes
`ORS-001` through `ORS-009` while keeping normalized business outcomes separate
from API, native-checkpoint, and PostgreSQL execution evidence. Native MAF
continues to own checkpoint bytes. Real downstream guarantees remain unverified
and blocked by #32.
A fresh external generation passed 136 backend tests, 10 frontend tests plus
build/CSP, all nine canonical scenarios without skips, 20 repeated concurrent
duplicate-request runs, source-independence checks, and Compose root
`200`/health `204`/protected API `401`. Exact-head CI and independent review
remain required before merge consideration.

Draft [PR #43](https://github.com/ppenumatsa1/agent-blueprints/pull/43)
integrates the versioned evaluation dataset, native MAF local deterministic
checks, merged #39 result normalization, and a generated evidence producer.
A fresh external generation passed 147 backend tests, all nine canonical
scenarios without skips, 10 frontend tests plus production build/CSP, and
Compose root `200`/health `204`/protected API `401`. The evidence producer
reported every scenario plus deterministic technical and business evaluation
as `passed`; the independent validator correctly retained an `unverified`
gate because no trusted producer attestation exists. Real provider/model
quality, actual browser evidence, and trusted provenance remain unverified,
and release/deployment remains blocked.

**Milestone decision:** READY for the local MAF software-factory milestone;
NOT READY for production, release, or deployment.

## Azure/Foundry Workstream C

Workstream C composes the generated FastAPI application with either the
existing native local host or Agent A's API-only native Responses bridge copied
into the generated backend. The API image does not import the sibling hosted
runtime or hosting SDK, and hosted composition fails closed when the bridge is
absent. The
application owns end-user authentication/authorization and PostgreSQL
business state; Agent A owns hosted execution identity and checkpoint/session
state. The API UAMI is the sole PostgreSQL runtime principal and is never
treated as the user. The hosted identity calls only the protected internal API
with the fixed `Hosted.Workflow.Invoke` app role and receives no database
configuration. PostgreSQL-only synthetic effects use a distinct application
tool identity and retain proposal/action/destination/digest binding.

Implementation acceptance criteria:

- explicit host selection with no local fallback from hosted errors;
- validated end-user tenant, issuer, audience, subject, scopes/roles,
  ownership, reviewer authorization, and stale/conflicting decisions;
- claim-before-send and authoritative status reconciliation for ambiguous
  hosted acknowledgments, without replay;
- app-only tenant/issuer/audience/principal/role validation on
  `/api/internal/hosted/v1`, case-bound conversation/channel checks,
  and durable idempotency-key conflict detection;
- authenticated-human start/resume prebinding before Responses dispatch,
  verification-only service-MI binding routes, and a hashed expiring decision
  intent that the hosted callback must match before recording a decision;
- opaque platform user/session/call correlation that cannot grant human
  authority, with current durable binding reauthorization on every
  verification request and platform call IDs excluded from business-operation
  digests;
- exact post-terminal human decision retries that reauthorize the reviewer,
  conversation, channel, intent, and command, then return Agent A's recorded
  Responses result without redispatch or another effect;
- explicit migrations, startup schema validation, runtime/admin identity
  separation, TLS verification, bounded pools, and managed-identity or secret
  authentication;
- a readable Debian CA bundle plus
  `SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt` in the canonical and
  generated API images so bundled libpq/OpenSSL can honor
  `PGSSLROOTCERT=system` under `verify-full`;
- unchanged frontend/API and ORS-001..009 contracts, atomic stores and effect
  ledger, and no duplicate synthetic effects; and
- local PostgreSQL/native Responses-wire tests plus generated-project and
  frontend checks.

The Agent A integration additionally uses `HttpHostedBusinessStore` for
case-bound prepare/claim/effect/finish calls and C's
`PostgresOperationJournal` beside `ResponsesClient`. These seams persist
business approval state and opaque correlation only; they never fabricate
local checkpoint IDs, expose PostgreSQL to the hosted runtime, or store
Foundry checkpoint bytes. The API-side `PostgresHostedAuthorityBindings`
adapter never derives user authority from opaque hosted correlation or case
fields.

Current local evidence satisfies those implementation criteria and is detailed
in [application security](azure-foundry/application-security.md) and draft PR
[#48](https://github.com/ppenumatsa1/agent-blueprints/pull/48). OBO is not
required because no verified user-delegated downstream operation exists.
Remaining work is integration review, exact-head CI, Agent A contract
confirmation, Agent B output binding, and live Azure/Foundry/PostgreSQL
verification. This workstream does not provision, deploy, merge, or close
production-readiness issues.

## Azure/Foundry Workstream B

Workstream B prepares, but does not execute, the Azure deployment path. Its
source of truth is [`.azure/deployment-plan.md`](../.azure/deployment-plan.md),
with the detailed inventory, regional evidence, cost assumptions, role matrix,
operations, and cross-workstream outputs in
[`docs/azure-foundry/infrastructure.md`](azure-foundry/infrastructure.md).

The selected single region is East US 2. The model contract is
`gpt-4.1-mini` version `2025-04-14`, `GlobalStandard`, capacity 10. The
subscription and platform checks found sufficient capacity, but Standard
`gpt-4.1-mini` quota is exhausted and is rejected. East US and Central US are
reviewed fallbacks only; failure in East US 2 stops the deployment and
requires a complete fallback-region recheck rather than silent resource
splitting.

The implementation provides modular Foundry/model, identity/RBAC,
observability, ACR, Container Apps, Key Vault, and PostgreSQL Bicep;
infrastructure-only root azd metadata; guarded Azure CLI preflight, what-if,
generated-application deploy, database configuration,
migration, health, rollback, and teardown scripts; and non-deploying contract
tests. Deployment instantiates a new independent Order Resolution project,
publishes its Agent A hosted source without ACR, and builds only its generated
Agent C API/frontend contexts in ACR.

Deployment-time Entra automation idempotently creates or reuses the authorized
single-tenant API/SPA registrations, exposes only the three workflow scopes,
defines user/approver roles, and creates no secret or test user. Live app
deployment fails closed when any generated Agent A/C interface is absent. The
cloud route requires hosted mode, managed-identity PostgreSQL with TLS
verification, an explicit hosted adapter endpoint and fixed agent name, and an
exact temporary-copy nginx upstream replacement. It prohibits source-blueprint
runtime paths, local workflow hosting, synthetic application selection, and
file checkpoints. The API UAMI is the sole database runtime principal. Hosted publication occurs
after the protected API state boundary is deployed, captures the authoritative
pending identity, assigns only a dedicated API application role, then requires
the same journaled version active without another create. Foundry Agent
Consumer scope is derived only from the validated project resource ID and the
same fixed publisher agent name; no scope input or project/subscription fallback
is permitted. The hosted app role is service authentication only; exact
API-owned human principal/case authority bound to the server-selected
conversation and channel must precede Responses dispatch. Foundry
user/session/call values remain opaque platform correlation rather than human
authority; the bridge does not send caller-selected session or actor metadata.

**Acceptance evidence:** exact base verified; read-only Azure discovery
completed; Bicep build/lint and 17 infrastructure contracts pass; 68 root tests
pass with two expected adapter-selection skips; script syntax checks pass.
Exact final A `708a4185` plus final C `722fc4e3` (all-six CI run
`45087843018`) generation produced
byte-identical owned files, built the canonical no-dev backend, imported the
bridge, and passed nonconnecting composition. The integration coordinator
independently reports default Docker CMD/app lifespan passed against isolated
PostgreSQL 17 with inherited image CA setting, verified TLS, health `204`, and
protected `401`; hostname and trust negatives failed closed. B did not rerun
that suite. The exact generated web image also built with
credentialless HTTPS npm proxy, unchanged `npm ci`, production Vite build, and
CSP verification. C's TLS code parent `509fb0b2` owns the canonical image
`SSL_CERT_FILE`; B deploy contracts
prohibit overriding the image default. Canonical packaging evidence is
complete. Live Azure composition is not proven.
The current Azure CLI identity matches the authorized target, but azd is a
different account and tenant. Azure CLI mode reports that mismatch without
blocking; explicit azd mode still fails closed. No Azure mutation or deployment
has occurred.

**Next action:** independent validation on the draft PR, then an approved
Azure CLI provider what-if with exact deployment inputs. Deployment remains
outside this PR.

Specification Studio has not yet produced an artifact, so the proposed
handoff is not an end-to-end compatibility claim. Phase 0 does not implement
the validator or an agent template, integrate Specification Studio, deploy
Azure resources, or establish production/customer approval.

## Phase 1: MAF workflow golden path

**Goal:** a reusable, independently runnable MAF workflow blueprint and an
independently buildable generated project, with durable human approval and
recovery and an independent Verification/Readiness Validator. Start locally
with FastAPI, React, PostgreSQL, Docker Compose, tests, and evaluations.
Business logic is supplied by the generated application; order adjustment is
only a synthetic test fixture. The primary deployment targets a Foundry
Hosted Agent for the native workflow, with separate Azure Container Apps
(ACA) for the UI and API. Hosting the workflow itself in ACA is a deferred
alternative, not a verified fallback.

The local workflow uses MAF-native file checkpoints on a persistent single-host
volume, separate from PostgreSQL business state and approval records. A future
Foundry host owns its managed checkpoint provider; the adapter and hosted
pause/resume validation are P1-12, not local durability evidence. Interactive
sign-in uses Entra ID and existing registrations, while isolated automated
tests may use synthetic identities. Azure provisioning requires explicit
approval of the resource inventory, estimated cost, and deployment plan.

### Reconciled gaps and sequencing

The engineering foundation and [integrated review #17](https://github.com/ppenumatsa1/agent-blueprints/pull/17)
are not proof of completed hosted or deployment capabilities. Track the
remaining acceptance criteria, dependencies and evidence in these issues:

- Hosted security and durability: [#22](https://github.com/ppenumatsa1/agent-blueprints/issues/22),
  [#19](https://github.com/ppenumatsa1/agent-blueprints/issues/19),
  [#20](https://github.com/ppenumatsa1/agent-blueprints/issues/20), and
  [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32).
- Reusable MAF extension contracts (P1): [#35](https://github.com/ppenumatsa1/agent-blueprints/issues/35)
  covers typed model, agent, prompt, tool/authorization, and executor/workflow
  patterns, demonstrated in a generated synthetic application.
- Independent trust and evaluation: [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21)
  and [#25](https://github.com/ppenumatsa1/agent-blueprints/issues/25).
- Azure, data, telemetry and identity: [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18),
  [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24),
  [#26](https://github.com/ppenumatsa1/agent-blueprints/issues/26),
  [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27), and
  [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28).
- Developer experience and demonstration: [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23)
  and [#29](https://github.com/ppenumatsa1/agent-blueprints/issues/29).
- P1 permanent standalone reference application: [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30)
  is required but requires separate repository authorization.
- Reusable MAF extensions and PostgreSQL readiness: [#35](https://github.com/ppenumatsa1/agent-blueprints/issues/35)
  and [#38](https://github.com/ppenumatsa1/agent-blueprints/issues/38).
- Separately scoped/future work: [#31](https://github.com/ppenumatsa1/agent-blueprints/issues/31),
  [#33](https://github.com/ppenumatsa1/agent-blueprints/issues/33), and
  [#34](https://github.com/ppenumatsa1/agent-blueprints/issues/34).

Merged PR [#40](https://github.com/ppenumatsa1/agent-blueprints/pull/40)
adds the standardized Order Resolution specification. Its focused executable
fixture remains separate from the current blueprint runtime and from the
legacy order-adjustment scenario. A framework mapping must consume the
normalized fixture and add native checkpoint/execution evidence rather than
redefining the business contract.

Hosted recovery remains explicitly deferred, not waived. Azure deployment
requires the implemented and independently verified offline prerequisites,
separately approved subscription access, and approval of the concrete
deployment plan. Read-only subscription and resource-group listing succeeded;
this is not evidence of deployment write access or application/service
connectivity. Its live checks provide evidence to close the related hosted and
operational issues.
Do not merge overlapping workstream histories blindly or treat a green
engineering check as release authorization.
The dated [issue and fix journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-22---issue-and-fix-status)
summarizes open PR evidence, unresolved issues and the review sequence. Its
draft work is not represented as merged functionality on this branch.

The #35 extension workstream keeps only seams that add application-owned
configuration or policy beyond MAF's native APIs. `ModelSelection` is a small
validated provider/model configuration value; the application constructs the
selected `SupportsChatGetResponse` client and passes it directly to MAF
`Agent`. `PromptAsset` supplies an explicit file version and source-byte digest
because MAF accepts instructions but does not manage versioned prompt files.
The example uses MAF's native `Agent` and `@tool` APIs directly; only the
request-scoped `ToolAuthorization` protocol remains application-owned, since
MAF tool registration is not business authorization. No generic
`ModelClientFactory`, `AgentDefinition`, `build_chat_agent`, or `ToolRegistry`
is needed. The workflow continues to use the host's `WorkflowFactory`,
framework-native `Executor`/`WorkflowBuilder`, and host-provided
`FileCheckpointStorage`.

The pinned `foundry-public` source at
[`4543075`](https://github.com/ppenumatsa1/maf-monorepo/tree/45430753c5f3e75716ea3822d2b2b52fbb4f1c34/agents/underwriting/foundry-public/backend)
likewise constructs its provider client in application code and builds
concrete MAF executors with `WorkflowBuilder`. Its client fallback is not
copied: unavailable model calls must not silently produce synthetic output.
The evaluation extension does not duplicate MAF's native `Evaluator`,
`LocalEvaluator`, `@evaluator`, or `evaluate_agent()` APIs. Applications use
the standard framework path and may pass its results to app-owned readiness
normalization.

The generated synthetic fixture tests provider selection, explicit versioned
prompt loading, native agent/tool composition, affirmative authorization,
approval/rejection and restart/crash recovery without invoking a real model.
The fixture tool is read-only. Arbitrary trusted Python callbacks remain
unsandboxed, so the absolute extension non-bypass criterion is unverified.
Consequential remote effects remain blocked by #32; hosted identity,
checkpoints and recovery (#19/#20/#22) and trusted readiness evidence (#21)
remain unverified. Do not mark #35 or hosted capabilities complete beyond the
evidence on the current draft PR.

The #25 follow-on retains only typed application-owned evaluation datasets,
rubric criteria with explicit thresholds, readiness-check identity validation,
and normalization of standard MAF evaluation results. Applications invoke
native MAF evaluation APIs directly; this extension adds no evaluator protocol
or orchestration wrapper. Callers supply unique IDs from the selected
readiness contract to validation and mapping; these are a consistency input,
not trusted authorization. Matching but unknown dataset/rubric IDs reject
before native evaluator invocation. Oversized integer thresholds reject and
oversized observation scores fail closed. Missing observations and unavailable
native results remain unverified; failed, malformed, unknown, or duplicate
observations cannot pass. Provider/tool errors propagate through the standard
framework path. Source and generated tests exercise MAF's native local
evaluator with explicitly synthetic responses, not live model quality. No
actual model or browser evidence, independent trust/provenance, or hosted
validation is claimed.
The stacked #37 base `0772af8c9ee0e5f765040f4d20ceab9962948c0d` passed all six
exact-head CI jobs in run [45031304964](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45031304964).
This only verifies #37's extension foundation; it does not establish real
evaluation, browser evidence, trust, or hosted readiness. PR #39's previous
head-specific CI is historical and does not validate this integration. On the
local integration tree, source and independently generated backends each passed
93 tests, both Ruff checks passed, the generated verifier passed 44 tests
without skips, and the root verifier passed 56 tests with one expected
`adapter-not-selected` skip. The pinned `agent-framework-core==1.26.0` wheel
matched the approved SHA-256 `175b75f07e15d1bb7b6cea9cb35b965ac2528cd96e3eae8f791c85c48c7232b3`.
These results correspond to implementation commit
`1724f3ef9bfdb7af07c575697cc1d0cd7b5d5af2`, whose exact-head Actions run
[45033947068](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45033947068)
passed all six jobs. This validates the evaluation implementation, not live
evaluation, browser evidence, trust, or hosted readiness. Subsequent
documentation-only commits require their own exact-head CI.

### Execution sequence and work packages

The modularity foundation reorganizes the local blueprint and generated
copies into sibling backend/frontend contexts and separates backend
responsibilities using canonical imports and no compatibility aliases. Acceptance
requires source and generated security/recovery tests, both crash windows,
independent golden verification and exact contract bytes, credential-free
CI and Compose smoke checks. Local evidence is recorded in the
[checklist](master-checklist.md). [PR #11](https://github.com/ppenumatsa1/agent-blueprints/pull/11)
merged into `main` as `de1cbe4`; its security-hardened head is
`587e6cc1abc23a67845c8193d486cc65c8b52854`. Foundation commit `9efeef0`
removes compatibility aliases and corrects checkpoint selection. Its
[hosted run 44936094798](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44936094798)
passed all five checks on that exact commit. An intermittent local restore
failure occurred during migration testing; a deterministic equal-timestamp
reproduction showed a real selection defect but does not prove the
unretained original failure had the same cause. The foundation selects
MAF-native persisted checkpoints and rejects incomplete terminal state on
completion and replay. Local source/generated backend suites passed 36 tests
each; the selected-adapter root suite passed 46 and the generated verifier
passed 44 without skips. Reconcile dependent PRs and verify the combined
revision separately. Hosted checks do not prove live hosting.
An independent CI regression exposed that the generated-verifier command's
failure could be masked by `tee`. The workflow now propagates pipeline
failures and the [regression test](../tests/test_ci_workflow.py) exercises
failure, skip and success behavior. Prior CI job status alone is not proof
that the verifier passed; logs for the prior PR heads recorded 44 tests and
`OK`. [Run 44939172266](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44939172266)
passed all five jobs for foundation head `d0e1727`. The dependent PRs had
separate successful head-specific runs, which are not evidence for the
reconciled tree.
PR #17 is merged into `main` at
`0c1297cc8e93c62f69d61d0eb3bdabf3c27c683d`; exact-main
[run 45027884271](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45027884271)
passed all six jobs for that baseline. PRs #36, #37 and #40 are now merged
into current `main` at `49932ee0cd61ee653a5f86be0f43873cec197ff9`; exact-main
run [45041465032](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45041465032)
passed all six jobs. PR #39 is being reconciled directly onto this main
revision without replaying #37. Earlier PR #17 commit and merge-ref results
below are historical snapshots and do not replace current-base validation. Local
validation and network/harness caveats are recorded in the
[integration journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-22---main-reconciliation-and-local-validation).
The [targeted MAF supply-chain audit](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-22---targeted-maf-supply-chain-audit)
distinguishes the approved `agent-framework-core==1.26.0` dependency from the
compromised `agent-framework` umbrella releases. Source and generated installs
must reject the umbrella distribution and verify the approved core wheel hash
against the canonical `uv.lock` before locked installation.
The copied evidence producer observed approval and recovery passing while
explanation and browser hint remained unverified; the independent unsigned
readiness report remained unverified. The first local container build could
not reach the public Python package host; a retry using the operator-approved
package proxies built and passed the generated Compose smoke checks.
Independent workstreams cover locked tooling, migrations, observability,
Foundry hosting, infrastructure and integration evidence. Do not merge PRs
without approval. Azure deployment is a deliverable but requires prior
approval of its resource inventory, estimated cost and deployment plan;
permanent reference repository creation requires separate approval. As of
2026-11-21, locked tooling is proposed in open
[PR #13](https://github.com/ppenumatsa1/agent-blueprints/pull/13), currently
at `7325765cbbfb809e2064ec0e78a5567b465e3621`. Actions run
[44947297321](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44947297321)
passed all five jobs on that exact head. The owner reports a headless
generated-project debugpy/DAP smoke using `.vscode/launch.json`'s
`Backend: FastAPI` configuration: execution stopped at `health.py:9`, the
stack was inspected, and continuing returned HTTP 204 with exit code 0;
temporary resources were cleaned. The report did not identify an immutable
revision. It does not verify the interactive VS Code UI, Restricted Mode, or
macOS.

Earlier, the owner reported Windows/Linux Compose verification using an
approved mirror after public TLS failures and could not run uv in a separate
validation environment. PR #13's previous reported head was
`b78634b3b746c7adbf5f8500e4b7023c96c67963`; its
[run 44928260607](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44928260607)
passed five checks for prior exact revision
`e1d953662e615e547fa641ad0831907c363318e3` only. The integrated tooling
revision is `543b137a432ca054920d629b943fc42a729df676`; its
[run 44937692067](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44937692067)
passed five checks for that exact head, not the combined PR #17 tree. None of
these results establishes that tooling is merged or validates this branch,
interactive debugging, Restricted Mode, or macOS.

For PR #16, the owner reports guarded Alembic adoption only after exact
baseline-manifest validation and checking that no later-revision-owned tables
exist; fresh databases run revision `0001`, and validation never stamps.
Source/generated suites each passed 48 tests on PostgreSQL 16.15 and 17.12;
the root suite passed 47 with one expected adapter-not-selected skip. Run
44944613749 passed five jobs for `897aae8` against `d0e1727`, but is stale
relative to foundation head `8144918`; reconcile and rerun before relying
on this evidence. Follow-up commit `ce86252324dca041fd5430602a3fc2c28a355274`
was reported to pass 12 focused migration regressions on isolated PostgreSQL
17 and Ruff 0.14.13 checks. It is local integration evidence, not final
combined CI; reconcile ancestry and validate the combined revision.
The owner later reported merge commit
`d1251352835c2d02e91690104b4dcabf465f5f05` with parents `897aae8` and
foundation `8144918`; its generated instantiation/link check, root suite
(47 passed, one expected skip), and all five Actions jobs in run 44947337144
passed. This is PR #16-specific and does not verify PR #17's combined tree.

Each PR must remove obsolete compatibility layers, use direct imports,
update affected `docs/design` specifications and the cumulative engineering
journal, and record actual regression, security, durability, independent
verification and CI outcomes for its final revision. PR #12 is deepening the
six generated-project guides and eight documents under
`blueprints/maf/workflow/docs/design/`; these documents must evolve alongside
implementation, remain in generated applications, and use actual
source/configuration references, meaningful Mermaid diagrams, and accurate
implemented/planned labels. An earlier documentation working tree passed three focused
instantiation and generated-verifier pipeline tests. PR #11 is now pushed at
`44ee18b886d409b0b59cf6df6b4893917370307d`. Its canonical source separates
`composition.py`, `api/app.py`, route handlers, schemas, dependencies,
errors, middleware, and `lifecycle.py`; the current PR #12 source-map links
now point to these exact paths. The owner reports 37 backend tests passed.
Actions run 44944929394 completed with four jobs passing and `contracts`
failing on the stale `specs.md` API link; the root suite had 47 tests, one
failure from that link, and one expected adapter-not-selected skip. Rebase
onto the new head and rerun root/contracts before final PR validation. The
coordinator reports the minimal link correction was then pushed at
`814491811eac457826108b70fc213fdc564af0e5`; root tests passed 47/47 and
Actions run
[44945419570](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44945419570)
passed all five jobs on that exact head, including generated checks without
skips. PR #12 is rebased onto that tip; its isolated root suite passed 47
tests with one expected adapter-not-selected skip, including generated
copy/link and verifier-pipeline tests, and `git diff --check` passed. Actual
head run
[44946550709](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44946550709)
passed all five jobs on exact head
`c247bf737acabe47e7af0023eaebf69c0b393fdf`. Hosted checks for this combined
PR #17 revision remain to be run.
Maintain the
engineering journal without inventing historical findings. For each meaningful PR update
this plan, `docs/master-checklist.md`, and relevant architecture documentation
with acceptance criteria, evidence, status, and next action.

### Cross-cutting PR acceptance gates

Before any PR is ready for approval, keep one canonical implementation and
use direct imports. Remove compatibility shims, forwarding modules, legacy
import aliases, obsolete directories, duplicate code, unused dependencies,
and stale configuration; backward compatibility with prior internal
implementations is not required for this greenfield blueprint. Update
dependent call sites, tests, Dockerfiles/build contexts, CI, documentation,
and instantiation scripts in the same coherent change while preserving
functional behavior and verification contracts.

Before requesting approval, run applicable regression, security, durability,
and independent verification tests; do not weaken or relabel failed or
unverified checks. Confirm GitHub Actions for the actual PR head revision.
Live Entra/OBO, Foundry-hosted recovery, cloud telemetry, and Azure deployment
remain unverified until separately implemented and evidenced. Azure
provisioning and permanent repository creation still require separate
authorization; never merge automatically.

The dependent developer-tooling branch adds `backend/pyproject.toml` and a
public-registry `uv.lock`, locked development and container installs, Ruff,
portable development commands and VS Code configurations. Acceptance requires
source and generated lint/tests and locked builds without Azure credentials,
then passing hosted CI on the actual reviewed head. Local Windows source and
generated backend tests, Ruff, generated UI tests/build and Linux Compose
204/401 smoke passed using an approved temporary mirror after public artifact
downloads failed locally with a TLS handshake error. On foundation `9efeef0`,
source and generated backend suites passed 36 tests each, independent
verification passed 44 without skips, generated frontend passed 8 tests/build/
CSP, and Ruff passed in both backends. Hosted run
[44940616666](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44940616666)
passed all five jobs for PR head `b78634b`, not for any combined revision.
macOS, interactive debugging and a clean public-only local installation
remain unverified. Next verify integrated work and review the separate PRs.

The migration workstream, based on `modularity-foundation`, adds Alembic
baseline `0001`, per-revision catalog manifests, an explicit schema-owner
upgrade and read-only startup validation. Local PostgreSQL 17 evidence:
12 migration tests including a test-only second revision, 43 source and 43
generated backend tests, 44 generated verifier tests, and two generator tests
after rebasing; source and generated Compose smokes each returned UI 200,
health 204 and protected API 401. The
[migration tests](../blueprints/maf/workflow/backend/tests/test_migrations.py),
[operations guide](../blueprints/maf/workflow/README.md#business-database-migrations)
and [journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md) record
the acceptance evidence and limitations. Two later local evidence runs failed;
their subprocess stderr was not retained. An independently reproduced native
checkpoint timestamp-tie defect was fixed in foundation `9efeef0`, whose
[CI run](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44936094798)
passed all five jobs. The original failures' causes remain unproven. Local
PostgreSQL 16.15 migration tests passed at `031fdb4`, after an initial
auxiliary readiness probe failed before tests.
At `7cd99ac`, local source and independently generated backend suites passed
48 tests each on both PostgreSQL 16.15 and 17.12; the generated verifier
passed 44 and generator tests passed two. The generated evidence producer
passed approval/recovery observations but left explanation/hint unverified;
the independent unsigned readiness report remained unverified.
[PR #16](https://github.com/ppenumatsa1/agent-blueprints/pull/16) remains open;
[run 44940559106](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44940559106)
passed all five jobs for head `eb898f6`, not on the combined
revision. Next verify the integrated revision; live backup/restore remains
unverified.

P1-14 now has a staged, independently copied
[Foundry-first resource graph](../blueprints/maf/workflow/infra/README.md)
and offline compiler/configuration tests. Optional model, project-wide API
agent-consumer grant, registry and API/UI services default off; the remaining
resources would still incur cost. Foundry and monitoring private connectivity,
PostgreSQL Entra token use, API/UI binding and the hosted-agent contract are
not implemented or verified. Source and independent generated static checks
and nine infrastructure security/configuration tests per copy passed locally
on the rebased working tree; two instantiation tests also passed.
[PR #15](https://github.com/ppenumatsa1/agent-blueprints/pull/15)
[run 44939817209](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44939817209)
passed all six jobs for head `2023e16`. Follow with separately authorized
network, identity, cost and deployment review; no cloud mutation has occurred.

The staged PostgreSQL server selects 16 while Compose uses 17. The pinned
API's documented enum and examples
conflict, and the compiler accepts arbitrary version strings; neither resolves
17 support for that API. The [version-gap review](../blueprints/maf/workflow/infra/README.md#open-postgresql-version-gap)
records a newer API as an unverified candidate. Separately, migration revision
`031fdb440908092cf09801232fe7f5d15048f065` passed 12 migration tests on local
PostgreSQL 16.15 after an initial auxiliary locale probe failed and was
corrected. The integration worktree combines the migrations and infrastructure,
but that result belongs to the separate migration revision. Resolve the target
major before deployment; local evidence does not prove Azure compatibility or
safe downgrade.

The local combined code revision `af3955a85036d3a6a01465648437a184a790309c`
passed 68 source and 68 generated backend tests on each of PostgreSQL 16.15
and 17.12, 47 selected-adapter root tests, 44 generated verification tests
without skips, Ruff, frontend tests/build/CSP, offline IaC checks, and source
and generated Compose smoke. Its unsigned readiness report remained
unverified. The [integration journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---combined-engineering-layer-integration)
records failed attempts and limitations. Exact final combined-revision CI
and review are still required; none of these open PRs has been merged.

P1-01 through P1-04 have an initial local foundation and a test-only
application adapter, but the scenario has no authorized contract approval.
Trusted result production and repository protection remain unverified. The
blueprint work follows the foundation in smaller reviewable changes. See the
[checklist](master-checklist.md) for status and evidence.

The [first blueprint increment](https://github.com/ppenumatsa1/agent-blueprints/pull/6)
contains a native MAF approval workflow, an explicit local host, PostgreSQL
decision/audit/action records, and integration tests including both
process-kill recovery windows. [Draft PR #8](https://github.com/ppenumatsa1/agent-blueprints/pull/8)
adds an Entra-secured API, MSAL UI, explicit synthetic application, and locally
smoke-tested Compose stack. A separate stacked increment adds a generator,
test-only golden adapter, fixture-specific evidence producer, and generated
project CI. It does not establish independently trusted result provenance,
live Entra/OBO, agent-generated explanation evaluation, browser hint
end-to-end behavior, or hosted recovery. A temporary generated copy passed
31 backend, 44 verification, and 8 frontend tests; its Compose stack passed
the local HTTP smoke check. Its unsigned readiness report is unverified.

| ID | Bounded work package | Dependencies | Independently verifiable outcome |
| --- | --- | --- | --- |
| P1-01 | Define the synthetic scenario, golden acceptance tests, and contract; obtain authorized approval. | None | [Scenario, golden cases, and test-only adapter](../scenarios/order-adjustment/README.md) exist; independent authorized approval remains outstanding. |
| P1-02 | Define normalized result, evidence, baseline, and signed-decision inputs; map actual runner output. | P1-01 | The [synthetic runner](../blueprints/maf/workflow/backend/tests/evidence_runner.py) records actual observations; independent result attestation remains outstanding. |
| P1-03 | Implement local traceability, evidence integrity, freshness, decisions, and profile gates. | P1-02 | [Validator](../readiness/validator.py) and [acceptance tests](../tests/test_readiness.py) exercise the policy; actual trust and provenance require independent administration. |
| P1-04 | Expose the validator as a local CLI with a machine-readable report. | P1-03 | [CLI](../readiness/__main__.py) and [usage](readiness-validator.md) preserve outcomes and disclose unapproved inputs. |
| P1-05 | Create a self-contained blueprint with the local React, FastAPI, PostgreSQL, and Docker Compose stack. | P1-01 interfaces | The stack starts; one temporary generated project builds, runs, tests, and verifies independently. Automated tests need no Azure credentials; interactive sign-in requires existing Entra configuration. |
| P1-05 readiness | Avoid the transient socket-only initialization race in source/generated CI and Compose. | P1-05 | [#38](https://github.com/ppenumatsa1/agent-blueprints/issues/38) records socket-ready/TCP-unready observations on disposable PostgreSQL 16.15 and 17, an initial `createdb` failure, and a 72/72 source/generated retry on historical head `8b3c357`. Both CI waits and the Compose health check use bounded loopback TCP readiness. [#17](https://github.com/ppenumatsa1/agent-blueprints/pull/17) merged as `0c1297c`; its exact-head [run 45027444227](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45027444227) passed six jobs, including source and generated Compose. #58's earlier head `9f9e16f` passed [run 45412773532](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45412773532); its same-tree head `787766c` passed seven jobs in [run 45418532803](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45418532803), as did #59 head `88de9e4` in [run 45419227019](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45419227019). Earlier #60 head `7398ad9` passed seven in [run 45444899975](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45444899975); later heads require their own CI. Review current-head CI and merge this reconciliation before considering #38 closure. Azure managed PostgreSQL readiness remains unverified. |
| P1-06 | Implement PostgreSQL business records, approval/audit state, and an idempotent action ledger for effects inside the same transaction. | P1-01, P1-05 interfaces | Real restart tests cover crashes after decision persistence and after action commit, with no unauthorized or duplicate database actions. Consequential remote effects are separately P0-blocked by [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32). |
| P1-07 | Implement typed FastAPI operations with Entra token validation, authorization, approvals, and optional OBO. | P1-01, P1-06 interfaces | Positive and negative tests cover scopes, roles, identity isolation, malformed and replayed requests; synthetic identities exist only in isolated tests. |
| P1-08 | Implement an accessible MSAL React client for sign-in, submission, status, approval/rejection, and failure states. | P1-01, P1-07 API contract | UI tests cover visible states and safe retries; browser code contains no service secrets. |
| P1-09 | Implement a native MAF workflow with local file checkpoints, isolated pause/resume, rejection, and recovery. | P1-01, P1-06 interfaces | Local tests cover repeated decisions, concurrent requests, and recovery without a universal orchestration wrapper; Foundry hosting is deferred to P1-12. |
| P1-10 | Add integration/E2E tests, synthetic agent evaluations, and GitHub Actions; connect actual results and artifacts to the validator. | P1-04 through P1-09 | Draft #43 generates revision-bound Order Resolution case, evaluation, matrix, input, and validator artifacts from the real generated adapter. All nine deterministic cases and separate business/technical checks pass locally; the independent report remains unverified without producer attestation. Real model and browser evidence remain outstanding. |
| P1-11 | Add privacy-safe logs, traces, correlation, and operational signals across API, workflow, approvals, and side effects. | P1-07, P1-09 interfaces | Manual telemetry tests cover redaction and correlation; owner-reported native global auto-instrumentation leaked a query canary and emitted duplicate FastAPI spans. Do not enable that path until exact-revision negative tests cover prompt/tool/identity and failure paths; hosted export remains environment-specific. |
| P1-15 | Demonstrate the local prototype from a synthetic specification through approval, evaluation, and its readiness report. | P1-10, P1-11 | Record the scenario, evidence, limitations, and observed elapsed time; the 2–3 hour objective is a target until a representative run demonstrates it. |
| P1-12 | Validate Foundry Hosted Agent compatibility for the selected MAF version, Responses protocol, request-aware workflow factory, identity, per-user session isolation, and host-managed checkpoints. | P1-09, P1-15 | Microsoft warns delegated users are not fenced from one another within a shared session. A trusted app must authorize each principal's session, verify mapping from the validated principal, map each authenticated caller to a distinct session, and reject unchecked client IDs; an opaque app-supplied `x-ms-user-identity` scoping value derived from that principal is not authorization. Platform-generated `x-agent-user-id` is a different header; do not assume their values match. Equivalence and binding to the validated principal are unsupported and unverified; this bridge and mapping are not implemented or tested. Local AgentServer Core 2.3.0/Responses 2.4.0 one-shot task IDs reran fresh after terminal completion and are not persistent deduplication; hosted semantics remain unknown. The exact `agent-framework-foundry-hosting==1.0.0b261112` source exposes `response_id` in the request-aware factory before checkpoint preparation/parsing/run claim, but this hook alone does not establish a safe owner-bound CAS claim, a reservation per continuation, pending-reply/action ordering, idempotent side effects, or same-response recovery. The scoping value is not a credential; hosted secret delivery/rotation and downstream OBO token lifecycle are not implemented, and end-user bearer/OBO tokens must not be persisted. Lost `response.id` recovery remains blocked; see the [investigation journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---hosted-caller-binding-and-lost-responses) and [session-isolation clarification](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---delegated-session-isolation-and-debugger-evidence). Local checks alone are not a hosted deployment. No Azure resources are provisioned. |
| P1-13 | Prepare the explicitly selected ACA fallback and a framework-compatible checkpoint strategy. | P1-09, P1-15 | Separate local/container recovery and idempotency checks pass; no claim that ACA shares Foundry checkpoint ownership or silently replaces a failed model call. |
| P1-14 | Prepare Bicep, least-privilege identities, authenticated public endpoints, GitHub-hosted CI, and deployment/handoff instructions. Deploy only after separate Azure authorization. | Offline: P1-10, P1-11, P1-12 design decisions; P1-13 only if selected. Live deployment supplies evidence for hosted/cloud issues and must not wait for all live-verification issues to be closed. | Exact PR #17 head `8b3c357` passed `maf-infrastructure` and generated infrastructure checks in run [44960731511](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44960731511); the staged graph is not wired or deployed. Track IaC wiring [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18), managed PostgreSQL operations [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24), and separately authorized live deployment [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28). |

### Current integrated review baseline and issue-linked backlog

The latest verified integrated snapshot is head
`8b3c3578f36c30f32f4539ef1d181e1ff3984ab4`, based on
`1e99e038dc31c0ae25e5ea7712030d204ee35bc0`. Run
[44960731511](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44960731511)
passed all six jobs. Merge ref
`2ab8f3c92ebde95aa5c0bfb2cd33b0e5ab558c52` had exact base/head parents and a
tree identical to the head (`304b2b02432bc8bf9a63b641c853e7f07467e860`).
Generated acceptance passed 44 tests without skips or expected failures.
Synthetic producer evidence remains limited: approval/recovery passed,
explanation/hint remain unverified, and the unsigned validator exited 1.
Any later tree or base change requires exact-head revalidation. Neither result
makes the blueprint, readiness report, or deployment complete. See the
[journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---integrated-gap-reconciliation-and-backlog).

| Work package | Open issue(s) and acceptance boundary |
| --- | --- |
| P1-01–03: authorized exact contract and independent trust/provenance | [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21); synthetic schemas and validator tests do not establish authorized approval or trust administration. |
| P0: consequential external side effects | [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32); the action ledger covers only effects in the same PostgreSQL transaction. Block consequential remote actions until service-specific authorization, downstream idempotency and authoritative reconciliation are independently verified; otherwise fail closed and use manual resolution. An outbox only persists intent; it cannot deduplicate an external effect after a lost acknowledgment. The opt-in [pattern](../blueprints/maf/workflow/backend/examples/external_effect_boundary.py) and [synthetic tests](../blueprints/maf/workflow/backend/tests/test_external_effect.py) cover exact-request authorization, a five-second downstream budget, conflicts, concurrency, timeouts, reconciliation and process death, not real services or hosted guarantees. Its case-level key represents one immutable action only; future proposal-version/action/target identity must follow merged #40. Independently verify generated revision and each integration's authorization, retention, timeout and reconciliation; keep #32 open. |
| P1-07–08: real identity and browser experience | [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27); interactive Entra/OBO, generated UI and accessibility remain unverified. |
| P1-09/P1-12: hosted MAF packaging and checkpoint integration | [#19](https://github.com/ppenumatsa1/agent-blueprints/issues/19); caller/session binding [#22](https://github.com/ppenumatsa1/agent-blueprints/issues/22); lost-response/effect recovery [#20](https://github.com/ppenumatsa1/agent-blueprints/issues/20). Hosted recovery was explicitly deferred; this is not a security waiver. |
| Typed MAF extensions | [#35](https://github.com/ppenumatsa1/agent-blueprints/issues/35), [merged PR #37](https://github.com/ppenumatsa1/agent-blueprints/pull/37); use validated model-selection configuration, explicitly versioned prompt assets, direct native MAF `Agent`, `@tool`, `Executor` and `WorkflowBuilder` composition, and request-scoped application authorization. The current #37 implementation was reconciled with merged #36/#40 behavior on main `49932ee0cd61ee653a5f86be0f43873cec197ff9`; exact-head CI and implementation evidence remain in its PR and merged records. The example requires affirmative `True` authorization. Arbitrary trusted Python callbacks remain unsandboxed, so absolute non-bypass is unverified. External effects remain blocked by [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32); hosted identity/recovery, trusted readiness and a live model response are not claimed. |
| P1-10: agent evaluation and browser-hint evidence | [#25](https://github.com/ppenumatsa1/agent-blueprints/issues/25); current synthetic producer leaves explanation and hint unverified. Applications invoke native MAF `Evaluator`, `LocalEvaluator`, `@evaluator`, and `evaluate_agent()` APIs. PR #39 adds only app-owned versioned datasets/rubrics, thresholds and readiness-check mapping/normalization; its synthetic local evaluation tests are not model-quality or browser evidence. Keep #25 open until actual evaluation evidence and independent provenance are available. |
| P1-11: privacy-safe cloud telemetry | [#26](https://github.com/ppenumatsa1/agent-blueprints/issues/26); native auto-instrumentation remains disabled after the query-canary leak and duplicate spans. |
| Developer experience | [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23); macOS, interactive debugging and Restricted Mode remain unverified. |
| P1-13: optional ACA workflow runtime | [#31](https://github.com/ppenumatsa1/agent-blueprints/issues/31); alternative remains unselected, not a silent fallback. |
| P1-14: Azure graph wiring, managed database operations, deployment | [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18), [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24), [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28); no Azure resource was provisioned. |
| P1-15: measured local demonstration | [#29](https://github.com/ppenumatsa1/agent-blueprints/issues/29); the 2–3 hour objective has not been measured. |
| Phase 0 Specification Studio handoff | [#33](https://github.com/ppenumatsa1/agent-blueprints/issues/33); no producer artifact or lossless adapter exists, and this does not authorize implementation. |
| P1 permanent standalone reference application | [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30); required as an independent deliverable, but repository creation still requires separate explicit authorization. |
| Later separate App/API blueprint roadmap | [#34](https://github.com/ppenumatsa1/agent-blueprints/issues/34); remains out of phase and requires separate authorization. |

### Azure/Foundry Workstream A

Agent A adds only the native hosted-runtime and lifecycle source boundary for
the independently generated Order Resolution application. Acceptance requires:

- exact public SDK pins and drift tests for the Responses host and
  `create_version_from_code`;
- a request-aware native workflow factory using Foundry-managed hosted
  checkpoints, never the API's local file store or a PostgreSQL workflow
  serializer;
- structured approval resume with application authorization, exact
  conversation/channel binding, and platform-managed session scope that never
  treats the API workload user as the human actor;
- an application-owned hosted business lifecycle that persists only opaque
  request correlation, decision, and completion while Foundry retains native
  checkpoint ownership;
- at-most-once-biased Responses and publish creates that preserve `unknown`
  after a lost acknowledgment, never resend a preexisting pending claim, bind
  the complete publication target/configuration identity, and require
  authoritative reconciliation;
- independent generator output plus focused hosted, local workflow and
  repository contract tests.

Implementation and current local evidence are recorded in the
  [hosting report](azure-foundry/hosting.md). On 2026-11-22, 40 generated hosted
  tests, 16 publisher/generator tests, Ruff, 39 focused generated PostgreSQL
  tests, ORS-001..009, and the 68-test repository contract suite (2 documented
  adapter skips) passed. The generated hosted total is now 41 after adding an
  acknowledged terminal-resume no-redispatch regression. Exact Workstream C
  revision `2a04d5be3013e782a7c1222b2a16a7047cbb15cd` passed a freshly generated
  real-PostgreSQL 17 protected-API business lifecycle and native
  `/conversations` plus `/responses` wire proof in 6.204 seconds, including
  normal API factory composition, restart duplicate acknowledgment with zero
  replay, terminal exact-intent replay with no new Responses dispatch,
  conflicting-intent and unauthorized-actor refusal, one decision/action,
  exact `OperationClaim(record, acquired)`, and null business checkpoint
  fields. C's six PR checks also passed in run `45084615221`. A binds human
  authority only to the authenticated case/conversation/channel command,
  treats platform user/session as separate opaque workload correlation, and
  omits caller-supplied `agent_session_id` so Foundry owns the stable
  conversation session. A exports the explicit
  `order_resolution_hosted.bridge:build_workflow_host` API-to-Responses
  factory; no generic `/runs` host is permitted. Agents B and D consume the
  explicit API-only runtime
  allowlist, atomic operation claim contract, and two-phase
  identity-then-active publication fields documented in the hosting report.
  Public hosted runtime never receives PostgreSQL connectivity; the protected
  API owns business persistence and database networking.
  This workstream does not provision Azure, assign roles, publish an agent, merge
  a pull request, or convert an unverified hosted capability to passing readiness.

### Validator acceptance contract

The validator consumes the approved, versioned verification contract; actual
normalized test/evaluation results; and supporting evidence artifacts. Its
assessment context supplies the target maturity, source revision, environment,
and assessment time. The first implementation reads bounded local artifacts,
not arbitrary remote URLs, and verifies their bytes and SHA-256 digests. It runs
locally or in CI with the generated project, not as a shared factory runtime.

It must verify the contract's exact byte digest against an authorized approval,
then account for every requirement and required check, matching reported IDs,
expected evidence types, results, revision, environment, and each check's
explicit freshness policy. Reject unknown or duplicate IDs, report missing
checks as unverified, and corroborate test outcomes with their actual result
artifacts. A failed check is **failed**; missing, stale, future-dated,
inaccessible, or mismatched evidence is **unverified**, never a passing check.
All blocking requirements must pass. Prototype readiness may still pass with
disclosed non-blocking failures or unknowns; production readiness additionally requires
verified, scoped, unexpired human risk acceptance for each such result.
Neither profile relabels failed or unverified outcomes.

Verify contract approval, applicability, classification changes, risk
acceptance, and customer decisions through an authorized human decision
mechanism, including scope, validity, and revocation; a name or approval
string alone is not authority. Compare changed critical/security-critical
classifications, removals, and applicability against the approved baseline and
require an explicit authorized decision for any downgrade. For production
and customer validation, enforce the declared security, integration,
operations, and evaluation domain coverage or a verified applicable
not-applicable decision. Missing production controls or unverifiable approval
cannot support a pass. Signed decisions and result attestations use an
independently administered, baseline-pinned trust store. Signatures establish
key possession, not human identity or actual execution; trust administration
and protected result production remain operator responsibilities.

For a valid contract and assessment context, write a machine-readable
readiness report even when checks fail or evidence is unverified. Exit zero
only for a passing report and nonzero otherwise. If the contract or assessment
context cannot be parsed or identified, emit a machine-readable diagnostic
and a nonzero exit rather than fabricating a schema-valid report. Tests must
cover missing or invalid contract approval, freshness boundaries,
revision/environment and digest mismatches, missing or duplicate IDs and
checks, critical downgrade attempts, failed tests, disclosed prototype
non-blocking failures, production risk acceptance with invalid scope or
expiry, missing production controls, unreviewed applicability, and missing or
rejected customer approval.

**Hosting constraint:** the Python Foundry hosting integration is documented as
prerelease. Establish package/protocol compatibility and the approval/resume
path before promising it. Foundry-managed checkpoints do not replace PostgreSQL
business state; ACA recovery requires separate evidence. Select a fallback
explicitly and never provision Azure resources without approval.

### P1-11 observability increment

The MAF backend now has manually instrumented request, workflow, database
operations and OBO boundaries, allowlisted JSON operational logs and optional
Azure Monitor trace and metric export. Missing or invalid hosted configuration
fails startup; subsequent export failures are signaled without changing workflow
outcomes. Metric dimensions are limited to operation/outcome and exemplars are
disabled. Span creation, metadata, context and closure failures are isolated
without retrying work or masking application exceptions; startup failures clean
up telemetry resources. Logger failures produce a fixed stderr-only failure
signal without payloads; a stderr write failure cannot change the workflow
result. Acceptance requires canary, correlation, injected SDK, logger and
export failure tests, credential-free generated-project CI, and no workflow
changes.
Evidence: [tests](../blueprints/maf/workflow/backend/tests/test_telemetry.py)
and [operational guidance](../blueprints/maf/workflow/README.md#operational-telemetry).
After reconciliation onto the checkpoint foundation, the source backend suite
passed 51 tests and the independent generated backend suite passed 56 tests
(including evidence-runner tests); the generated standalone verifier passed
44 tests and two instantiation tests passed. Recovery coverage includes tied
checkpoint selection, pending and terminal validation, and completed replay
rejection. Earlier Compose returned UI 200, health 204 and protected API 401
after an initial failed startup attempt. [PR #14](https://github.com/ppenumatsa1/agent-blueprints/pull/14)
head `8c643df` passed all five jobs in
[run 44938368000](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44938368000);
these checks do not prove cloud export or the combined revision.
This increment remains in progress pending review and real hosted
verification. Outbound/Foundry propagation, sampling,
retention, regional placement and access policy require separate validation.
The common design suite and engineering journal record the implementation and
limitations. The local integration tree combines the public locked telemetry
dependencies with tooling. Its source and generated backend suites passed 50
tests each, its generated verifier 44, and generation tests two; full Ruff
checks passed. Both backend images built with an approved mirror after public
Python TLS failures.
Revision `fe4550a` passed 50 source and 50 generated backend tests, the
44-test generated verifier, and two instantiation tests; changed Python files
passed Ruff with the tooling workstream's configuration. These historical
results are not combined-revision evidence. Hosted configuration and cloud
ingestion remain unverified. No Azure provisioning or ingestion is implied.

## API-boundary integration follow-up

The final PR #14 code from `3aa389f` is reconciled with migrations and the
canonical dependency lock. All 23 focused privacy regressions passed locally;
native automatic instrumentation remains disabled following the measured
query-canary leak. Complete source/generated and final-revision CI checks
before review; hosted caller binding and lost-response recovery remain blocked.

The PR #11 API split and source-map fix are being reconciled with integrated
telemetry rather than replaying earlier workstream history. The
[integration journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---reconcile-api-boundaries-with-integration-telemetry)
records focused local evidence and limitations. Acceptance still requires the
remaining workstream changes and source/generated checks on the final combined
revision; earlier runs do not establish that result.

The exact PR #16 delta `897aae8` adopts a validated existing baseline through
Alembic `stamp` inside the existing transaction; fresh schemas still execute
the baseline revision. Its 12 migration regressions passed locally on isolated
PostgreSQL 17 after restoring cached HTTP test dependencies, and locked-version
Ruff checks passed. This focused result is not final combined verification.
The design-document owner will consolidate the engineering journal.

## Later phases

| Phase | Scope and dependency |
| --- | --- |
| 2 | MAF harness and a Foundry Project SDK agent; choose prompt versus application-owned runtime explicitly and preserve application-controlled authority. Builds on Phase 1 contracts and evidence. |
| 3 | LangGraph workflow with native graph state, interrupt/resume, framework-specific checkpointing, and the same independent project/security expectations. |
| 4 | Deep Agents harness, with its own supported tools, hosting protocol, state boundaries, and evidence. |
| 5 | GitHub Copilot SDK harness, retaining the SDK-managed loop, explicit permissions, and independently verified hosting compatibility. |
| 6 | Specification Studio contract handoff and project generation, after the schemas and selected blueprints have been validated; generated applications remain independently deployable. |

App/API Blueprints and Specification Studio are separate future repositories.
Private networking and self-hosted runners are deferred work, not assumed
prerequisites for Phase 1. Each phase requires its own approval, implementation,
and evidence; this plan does not authorize deployment or create those
repositories.

## Azure/Foundry Workstream D

Workstream D adds only observability and evidence-producing/validating
capabilities. It preserves the six existing CI jobs and adds a generated
Chromium job. The separate cloud-validation workflow is manual,
revision-bound, and non-deploying.

Acceptance requires:

1. allowlisted API-to-PostgreSQL correlation with separate technical and
   business outcomes and no raw model, tool, identity, SQL, or business
   payloads;
2. explicit real-provider evaluation with no synthetic fallback;
3. actual local Chromium plus authenticated live browser evidence;
4. all nine hosted fault/recovery cases with unknown-outcome reconciliation
   and no hidden retry;
5. exact active revision/image/version and App Insights corroboration; and
6. independent implementation and Azure runtime diagnostics with immutable
   artifact hashes, plus a permanently non-authorizing production dimension
   that defers to the signed trust validator.

For an immediate Responses `status: failed` with an authoritative ID, the
client surfaces an error and persists the outcome; same-key retries, including
after a PostgreSQL-backed restart, must fail without redispatch. The generated
hosted API regression covers this contract without Azure. Apply the profile
migration before deploying the client fix. Keep later background failure,
safe HTTP 429 retry, and authoritative unknown-outcome reconciliation open
until verified against the hosted API.

The exact commands, GitHub environment inputs, evidence schemas, baseline CI,
region reference, current blocked/unverified matrix, and dependencies on
Agents A-C are in the [Workstream D readiness guide](azure-foundry/readiness.md).
Exact head `c63b48afa4179a3d92c286aeb6ae339e16ece275` passed all seven CI
jobs in run `45158642321`; the immutable API/web revisions and HTTP boundaries
also passed. The 2026-11-23 live attempt then preserved the remaining outcomes:
delegated workflow, provider, failure, ORS-001–009, and authenticated-browser
gates are blocked; telemetry correlation and normalized deployment evidence
failed. Next action: deploy exact runtime revision metadata, publish the
deployment artifact, and supply reviewed short-lived authentication and live
adapters before rerunning. Credential-free CI remains implementation evidence
only.

The PR #49 remediation now passes exact agent/deployment metadata into the
profile telemetry pipeline, returns a W3C `traceparent`, and reconstructs the
normalized deployment contract from acknowledged Azure state. Entra
configuration preauthorizes the Azure CLI public client and defines explicit
`Workflow.Approver` and `Acceptance.Operator` assignments. Bounded synthetic
acceptance controls are disabled by default, require the operator role, and
are bound to the exact hosted deployment revision. The live failure adapter,
ORS-001–009 result factory, Foundry model evaluator, and Chromium test all
require distinct delegated owner and reviewer identities; no application
identity or single-user bypass is permitted. Local evidence is 93 root tests,
11 focused generated tests with one explicit provider opt-in skip, locked Ruff,
Bicep build, frontend build, 9 frontend unit tests, and Playwright discovery.
Live outcomes remain unverified until the exact committed revision is deployed
and two short-lived delegated identities are available.

The subsequent authorized synthetic run established partial live evidence
without weakening that identity boundary. ORS-001, ORS-004, ORS-006, ORS-007,
all ORS-008 variants, and the ORS-009 owner authorization negative executed on
Azure. The formal App Insights verifier corroborated one exact
request/case/trace pair for hosted agent version `1` and deployment
`00f96360051daf8a505db221f95d6206c61b3746` with 16 telemetry rows and no
correlated exception. Deployment reconciliation independently recovered the
immutable API/web revisions and digests, acknowledged `order-resolution:1`,
and exact-agent RBAC scope.

Two acceptance-only defects were found and corrected: Windows Azure CLI
launchers and multiline/double-quoted KQL were not portable through `az.cmd`,
and the acceptance snapshot omitted `hosted_workflow_finished` from its
terminal-event count. Root validation now passes 99 tests with two disclosed
adapter-selection skips, and the generated hosted completion/idempotency
regression passes against isolated PostgreSQL. Live terminal normalization
must still be verified after deployment. ORS-002, ORS-003, ORS-005, positive
approval/rejection, reviewer-dependent crash windows, provider evaluation, and
authenticated dual-user Chromium remain externally blocked until a second
delegated Entra user has `workflow.read workflow.approve`,
`Workflow.Approver`, API consent, and an authenticated browser state. The
temporary PostgreSQL public rule remains required until a validated replacement
egress/firewall path is active.

The current observability remediation is built-ins-first and remains pending
live proof. Pinned AgentServer `2.3.1b1`, Agent Framework `1.26.0`, Azure
Monitor exporter `1.0.0b59`, OpenTelemetry `1.45.2`, HTTPX `0.28.1`, and
Azure Identity `1.27.0` APIs were checked before implementation. Hosted startup
now configures one AgentServer/Azure Monitor provider with supported Azure SDK,
HTTPX, and urllib instrumentation before enabling privacy-safe native MAF
instrumentation. The API reuses its global provider, injects W3C context into
Foundry, and deduplicates Azure Monitor processors by destination. Durable
start metadata records only W3C identifiers; resume emits an explicit OTel
link rather than claiming uninterrupted parenting. The verifier now requires
real hosted roots, connected parent trees, API/hosted role coverage,
conversation continuity, native/business spans, restart links, deployment
metadata, no raw content, and matching Foundry trajectory trace IDs. Generated
hosted compatibility and privacy tests pass locally; exact-head CI and live
App Insights/Foundry evidence are still required before this gate can pass.

The first hosted-version-2 trace proof isolated a request-finalization defect,
not a provider or propagation defect. Synthetic case
`c22d740f-0983-4d1f-b2c1-e7470aafe9f1` reached pending HITL under trace
`125933bf44624f04af77bb285814b53a`. Application Insights contained 37 rows:
five API requests and 32 dependencies, all under the API role. The five API
callbacks retained that OperationId but referenced absent hosted ParentIds.
There was no hosted role, enriched `invoke_agent`, native workflow span, or
business-stage span, and the raw-content count remained zero. A corrected
read-only Foundry query also returned zero hosted roots, so query parsing was
not the cause.

Official and pinned API evidence agrees on the smallest remedy. OpenTelemetry
documents W3C Trace Context plus library instrumentation for automatic
propagation. Azure Monitor recommends initializing its distro before work is
handled and not initializing parallel distros. MAF documents process-wide
providers configured once, application-owned provider setup followed by
`enable_instrumentation()`, and sensitive capture disabled by default.
AgentServer Responses `2.4.0` documents `background` as the default flush mode,
warns that it requires a platform drain window, and supports `async` to await
export off the event loop. The pinned implementation exposes exactly that
behavior. Therefore the publisher now forces
`AGENTSERVER_FLUSH_MODE=async`; it does not add an exporter, provider, sampler,
manual MAF span recreation, or synthetic model call.

Built-in behavior remains responsible for the global provider, Azure Monitor
export, resource metadata, native MAF spans, W3C propagation, HTTPX/urllib/Azure
SDK instrumentation, and request-awaited flush. Custom code remains limited to
privacy-safe application business-stage anchors and an explicit durable HITL
trace link, because OpenTelemetry cannot preserve an active parent context
across a serialized approval boundary. The separate Windows helper correction
uses KQL single-quoted trace IDs so `az.cmd` does not strip JSON quotes. Its
read-only live parse check exits zero; it still finds zero pre-fix hosted roots,
as expected. Validation passes 103 root tests with two disclosed adapter skips,
47 generated hosted tests, and Ruff. Exact-head CI, a new immutable hosted
version, and live connected trace evidence remain required.

The subsequent version-3 proof established that awaited flush was executing,
but Azure Monitor rejected every hosted export as `Unauthorized`. The existing
Application Insights component has `DisableLocalAuth=true`; the hosted
definition did not select AgentServer's Entra mode and the hosted-version
identity did not hold `Monitoring Metrics Publisher`. The compatible
built-in-first correction fixes
`APPLICATIONINSIGHTS_AUTH_MODE=entra`, which the pinned AgentServer
`2.3.1b1` implementation maps to `ManagedIdentityCredential()` through the
Microsoft OpenTelemetry distro. The staged deployment path grants role
`3913510d-42f4-4e42-8a64-420c390055eb` only at the exact Application Insights
component scope after hosted identity discovery and before active readiness.
Normalized evidence rejects a missing, broader, wrong-role, or wrong-principal
assignment. The API deployment binds `HOSTED_AGENT_VERSION` to the published
version and the application prefers that value for trace metadata while
retaining `AGENT_VERSION` as a compatibility fallback. Privacy flags remain
fixed false. Deployment and live proof remain separate later gates.
Local validation passes 103 root tests with the two disclosed adapter-selection
skips, 126 source-backend tests and 179 independently generated backend tests
against disposable PostgreSQL 17 instances, 48 generated hosted-agent tests,
Ruff check/format, PowerShell parsing, and Bicep compilation.

The first exact-head remediation run exposed a generated local-host regression
rather than an exporter failure: the workflow now persisted its deterministic
conversation ID, while `OrderResolutionWorkflowHost` still accepted only the
older case-only request payload. That strict mismatch converted every
approval-required start into fail-closed HTTP `503`. The host now validates the
complete case/conversation identity both on initial observation and checkpoint
restore. The generated PostgreSQL Order Resolution API suite, Ruff, and source
instantiation tests pass locally after the correction. The same run also showed
that the contracts-only source-independence probe imported the hosted bridge
after its supported OTel propagation dependency was added. That probe now
resolves the generated module path without importing runtime dependencies;
actual imports remain covered by the locked generated-project job. A new
exact-head CI run is still required before deployment.

The final deployment preflight review found one non-mutating orchestration
defect: `deploy.ps1` passed the directory operator object ID to
`preflight.ps1`, whose supported contract intentionally validates only the
Azure CLI identity, subscription, tenant, user, and region. The unsupported
parameter is removed, an infrastructure contract prevents its return, and the
live read-only preflight passes without changing the configured identities.

The first exact-head deploy attempt then stopped before preflight or mutation
because the repository-local working-root default contradicted the generator's
independence guard. Deployment now requires an explicit working root and
rejects the repository or any descendant immediately. The authorized retry
uses the session evidence directory, which is outside the source tree and not
an operating-system temporary directory.

The external-root retry completed the provider deployment, then exposed that
application-only redeployment still replayed the one-time PostgreSQL
configuration path. The Container Apps environment currently advertises more
than 400 possible outbound addresses, and serial Flexible Server firewall
updates cannot be part of each immutable application rollout. Deployment now
has an explicit `SkipPostgresConfiguration` path for an already configured
environment; it does not remove the temporary public rule, change database
roles, skip application health checks, or claim that controlled replacement
egress is complete.

The subsequent immutable application rollout built the API image but failed
closed at its first API update. On Windows, Azure CLI was reached through
`az.cmd`, which interpreted the `&sslrootcert=system` portion of the
TLS-preserving `DATABASE_URL` as a command separator. The API update calls now
invoke the Azure CLI packaged Python module directly on Windows and continue to
use normal `az` resolution elsewhere. Contract validation requires both API
updates to use this path; the TLS query string is unchanged. Exact-head CI and
live deployment evidence remain required before this correction is complete.

The authorized PR #62 existing-resource POC deployment subsequently completed
on candidate `3cfdbd942dc7daf37e4f8f136b26645b83471978`. Exact-head CI run
`45980935647` passed 8/8. Immutable API, web, and hosted images were published
without infrastructure, network, firewall, Entra, managed-identity, or policy
changes. Foundry image mode required two bounded corrections: platform-reserved
environment variables are omitted from the submitted image definition while
remaining journal-bound, and the image fixes AgentServer state under
`/home/hosted/.agentserver` because Foundry overrides `HOME`.

The final state is hosted version 11 fixed at 100%, API revision
suffix `pr62-3cfdbd9-v11`, and web revision suffix `pr62-3cfdbd9-v3`.
ORS-001 and ORS-004 completed with one
claim, one effect, and one terminal event; ORS-004 reused its request identity
without duplicating the terminal outcome. ORS-006, ORS-007, and all three
ORS-008 variants failed explicitly with their required policy evidence codes,
zero effects, and one terminal event. ORS-002, ORS-003, ORS-005, ORS-009, the
seven Azure Policy audit findings, provider/browser validation, and production
readiness remain unresolved. The deployment plan therefore remains
**Approved / Not Validated**.

Infrastructure redeployment must never infer an application image. The Bicep
entry point now requires explicit API and web images, and the guarded
orchestrator resolves existing applications before ARM deployment. Existing
images must be digest-pinned; a placeholder is allowed only when no immutable
revision exists. If ARM previously replaced a live template with the
placeholder while immutable revisions remain, deployment stops and requires
guarded application restoration instead of moving traffic again.

Hosted startup now preserves the supported AgentServer lifecycle order:
privacy settings are applied, AgentServer configures the Azure Monitor global
provider and HTTP instrumentation, native MAF instrumentation is enabled on
that provider, and only then is the application/MAF graph loaded lazily.
Durable waits retain only W3C trace/span identifiers and resume with an
explicit link. The strict verifier does not require model or token spans when
the deterministic path does not invoke a model.

The version-4 live proof then isolated the remaining root defect. Managed
identity export succeeded with zero Azure Monitor errors and produced 100
hosted dependencies plus 193 hosted logs, but 83 hosted spans shared a missing
remote parent and no enriched `invoke_agent` root appeared after repeated
ingestion polls. Pinned AgentServer core intentionally attaches incoming W3C
context without creating a SERVER span; Responses `CreateSpan` invokes no
OpenTelemetry API unless the public `ResponsesServerOptions.create_span_hook`
is supplied. Sampling, provider order, processing, flush and indexing were
therefore excluded.

The smallest supported correction supplies that hook and nothing parallel to
the native pipeline. It creates one privacy-safe application-owned INTERNAL
`invoke_agent` anchor under the remote platform context, makes it current for
native/business children, records only allowlisted identifiers plus
source/deployment revision, and ends before request-awaited flush. It records
ERROR and exception type without exception text. The verifier now requires the
exact hook marker, validates API and hosted subgraphs independently across the
documented platform-parent gap, and rejects duplicate roots, missing markers,
unexpected roles, and arbitrary hosted orphans. The external reference
`maf-monorepo` revision `45430753c5f3e75716ea3822d2b2b52fbb4f1c34` likewise
uses an application-owned handler span rather than a package-generated root;
it was inspected only as behavioral evidence. Local evidence is 103 root tests
with two disclosed skips, 53 generated hosted-agent tests, nine publisher
tests, nine infrastructure contracts, Ruff, and PowerShell parsing.

The immutable version-5 proof on revision
`acf2911b76b470d5b7254d97ba2b6934f5444ddb` passed for the safe start path.
Trace `9ff606620c4a4d728da127c531ffef40` contains one marked app-owned
`invoke_agent` root, 101 hosted spans and 37 API spans. All 136 emitted parent
edges resolve; the remaining two parents are the expected external caller and
non-exported AgentServer platform contexts. Foundry indexes the same root with
the exact conversation and version 5, while App Insights records the exact
case, deployment revision, project and session. There are zero correlated
exceptions, exporter failures, raw-content fields, synthetic payload leaks or
pending effects. The evidence tooling now queries both request and dependency
tables for the supported app-owned root and validates the two-component
distributed forest rather than incorrectly requiring one root per service.
Resume/link proof remains blocked on the distinct reviewer credential.

The release manifest cannot waive or authorize production checks; production
requires the baseline-pinned trust validator, signed result attestations, and
scoped, unexpired risk decisions, while critical/security-critical blocking
checks remain non-waivable.
