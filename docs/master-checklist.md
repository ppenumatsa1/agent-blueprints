# Software Factory master checklist

This is the living tracker for the three-repository Software Factory. Update
it, the [implementation plan](implementation-plan.md), and relevant
architecture documentation with each meaningful PR. Use **Planned**,
**In Progress**, **Completed**, or **Blocked**; mark work completed only
when it is implemented and supported by evidence. A plan link is a design
reference, not proof that functionality exists.

The original [interactive architecture](software-factory.html) is a preserved
historical source; this checklist records current status. The 2–3 hour
prototype objective has not yet been measured.

## Single-identity synthetic POC in PR #62

**Status: In Progress; Azure activation and acceptance remain blocked.**
Acceptance requires default-off behavior, the exact Entra operator and
application database/MI, an owner-issued grant for the exact pending hosted
proposal and outcome, an atomic protected audit, and no non-synthetic effect.
A disposable PostgreSQL fixture exercised approval/rejection, replay, revoked
trust from privilege drift, binding/payload tampering, expiry, and atomic
rollback using fixture Entra role labels. See the [operator
runbook](../profiles/order-resolution/overlay/backend/poc/README.md).
Next: review the candidate and verify the actual Azure application-database
principal mapping, role ownership, immutable deployed revisions and scope
before enabling the option. Neither production authorization nor firewall
rules are changed. Do not count unexecuted or multi-principal scenarios as
passed. The dedicated security review failed before producing a verdict and
must be repeated by an authorized reviewer before activation. A historical
API binary can act on a persisted self-approval without the new effect check;
binary rollback requires verified quiescence of all POC cases, grants,
effects, and sessions, not merely a clean journal.

## Explicit partial live acceptance in PR #62

**Status: Completed locally; deployed execution remains unverified.**
Acceptance: `create_results(case_ids=[...])` runs only explicitly selected
canonical cases, records every omitted case as `status: not_run`, and rejects
empty, unknown, duplicate, or unsupported selections before constructing a
live client. Default all-nine selection still fails closed on ORS-005.
Same-identity POC mode cannot select the distinct-actor ORS-009 oracle.
Evidence: three isolated generated-backend regressions passed on the change
based on `28b7da3541d4d24e2d7b5e6e76873d937c7c1349`. A later generated API
reproduction returned HTTP 422 for the old POC reviewer placeholder. Six focused
generated-backend tests subsequently passed with a stable reserved UUID,
collision refusal, and a mocked five-case driver that never grants or decides;
the complete 33-test acceptance module and Ruff checks also passed. An initial
format check failed before formatting was corrected. No live case was submitted.
Next: verify the integrated POC driver and record actual selected-case outcomes
without declaring omitted cases or the full matrix passed.

## Live acceptance oracle corrections in PR #62

**Status: In Progress; local checks passed, exact-head CI and Azure execution
pending.** ORS-004 must observe the same request identity while the case is
still nonterminal and compare the replayed terminal business outcome with the
original; a fast completion is `unverified`, not a pass. ORS-008 must observe
the actual invalid-evidence failure, no proposal, decision, action or recorded
approval request, and exactly one terminal event for every variant. Missing
or inconsistent evidence fails closed.

The previous driver reproduced false positives for these conditions in
focused generated-project tests. The corrected independent generation passed
38 acceptance tests and three PostgreSQL-backed tests, including local and
hosted approval-event accounting and all invalid-evidence variants. The
isolated root suite ran 114 tests with two existing skips. An initial format
check failed; the repository-specific formatter and lint checks then passed.
These results do not prove live Foundry execution, complete session visibility
or deployed provenance. Next: verify exact-head CI and the scoped deployment
and recovery prerequisites before collecting real selected-case evidence.

## Opt-in hosted image publication for PR #62

**Status: In Progress; local image path only.** Acceptance: independently
generated Order Resolution projects can stage the existing hosted source,
build a non-root `linux/amd64` image, and publish an explicit SHA-256 image
reference only while the endpoint has one recorded, fixed 100% prior-version
route. The existing remote source-build path remains the default. Ambiguous
creates cannot be replayed and trigger a route recheck; reconciliation also
rechecks the route on inconclusive reads. A version GET must report the
requested version and image.
Route reads are not atomic with creation and require coordinated single-writer
deployment. Neither an image reference nor an API observation proves source
provenance or the image actually executing in a hosted session.

Local evidence on base `28b7da3541d4d24e2d7b5e6e76873d937c7c1349`:
17 publisher tests, eight generated-project tests, 67 hosted tests inside the
image, and 114 isolated root tests with two existing skips passed. The pinned
SDK serialized the digest reference. A network-isolated synthetic-app probe
returned `200` from `/readiness` on port 8088. The first build against default
PyPI failed on a TLS handshake; a separate credentialless HTTPS mirror build
passed. The first image lacked a writable non-root home and failed server
construction; the corrected image passed construction. A healthz-only probe
timed out because `/healthz` returned `404`. The synthetic readiness probe
mocked prewarm and observability; a separate real-composition probe without
network or credentials logged authentication and telemetry initialization
failures, so it is not evidence of live identity or telemetry.
The credential-free CI workflow now runs the publisher regressions and builds
the generated hosted image; its network-isolated composition check mocks
prewarm and observability. This CI change has not run on an integrated head.

Next: integrate and independently review this change on the existing draft
[#62](https://github.com/ppenumatsa1/agent-blueprints/pull/62), verify its
exact-head CI, then use an authorized single-writer rollout and inspect the
registry, route, candidate configuration, identity and actual sessions. The
deployment orchestrator still defaults to remote source builds; no Azure
deployment, independent provenance, live acceptance or production readiness
is claimed. Existing failure-injection and release gates are unchanged.
Route restoration alone is not a verified binary rollback; see the POC
rollback constraints above.

## Windows asynchronous PostgreSQL startup in PR #62

**Status: In Progress; local acceptance passed, exact-head CI pending.**
Acceptance: the ordinary generated backend discovery command must exercise
the real asynchronous PostgreSQL security checks on Windows without a
process-wide policy override, skipped checks, or changed authorization.
At `1d36ebf0e920705c188344e7c15e9ca138706186`, the original three cases were
reproduced with two Psycopg Proactor `InterfaceError`s and one stream 503
assertion. Those failed runs remain evidence.

Windows tests now select native Selector loops through Python/AnyIO's scoped
`loop_factory` options; the process-wide policy is asserted unchanged.
Windows Uvicorn development/debug startup uses its supported
`--loop asyncio:SelectorEventLoop` option. Other platforms retain their
defaults; incompatible existing/embedded Proactor loops are not replaced.
Four focused checks passed, including real loopback Uvicorn HTTP activity
delivery and unauthorized-reader denial. The ordinary
`python -m unittest discover -s tests -v` passed 176 generated base tests
and 273 profile tests with one existing real-provider skip. Psycopg connection
ResourceWarnings remain disclosed. The isolated root suite ran 114 tests with
two existing adapter-selection skips; generated backend lint/format passed.
Selector socket/subprocess limitations
remain Windows development constraints, not proven production capacity.

Next: bind this candidate to exact-head CI on the existing draft
[#62](https://github.com/ppenumatsa1/agent-blueprints/pull/62).
Deployment provenance, firewall-preserving migrations and hosted recovery
gates remain unchanged and blocked.

## Hosted failure visibility and acceptance corrections in PR #62

**Status: In Progress; current-head CI and Azure validation remain pending.**
Acceptance: persist an immediate failed hosted start/resume and its case
failure/audit atomically without inventing a business outcome or checkpoint;
do not overwrite an existing failure, replay the failed operation, or authorize
a new decision against a recorded failed response. Delayed callbacks retain
the failure until a matching hosted completion. The UI hides decisions while
any case failure is displayed. The acceptance adapter waits for the actual
hosted handle and terminal state; passed failure scenarios require a successful
hosted-start claim correlation. Existing failures survive hosted callbacks
both before and after a failed operation is journaled; failed nonterminal
cases keep refreshing without exposing approval. Polling has a cancellable
60-second overall timeout, including reads. The protected acceptance endpoint
returns the server-generated request ID recorded on the original acknowledged
start claim; a replay or legacy claim without that ID cannot satisfy coverage.
A claim is not proof of outbound dispatch: independent telemetry and the
provenance gate remain mandatory. The full live nine-case producer stops
before submitting cases because ORS-005 native continuation is not
independently verified.

Local evidence on the follow-up candidate based on
`174eca3d9a6b02f5fe4d42f3e2ae4a360639d5c8`:
three generated API/MAF/PostgreSQL and Agent A loopback happy paths; all nine
canonical synthetic scenarios; 42 focused regression tests; generated base
backend 175 tests and profile backend 272 tests with one real-provider skip,
both under Windows Selector policy; hosted-agent 67 tests; generated base and
profile frontend 62 and 67 tests, builds and CSP; and Chromium local, history,
and production-studio checks of 1, 5 and 1 tests for each generated frontend.
Three real Docker isolation tests passed using the previously verified package
mirror, including approval, rejection, and capability-denial probes.
An additional loopback HTTPS probe observed a stalled response body time out
and the client socket close; this is not cloud-network evidence.
The isolated repository suite passed 114 tests with two adapter-selection
skips. These use synthetic identities, disposable local PostgreSQL, and a
loopback Responses fixture, not a deployment or live authenticated browser.

Earlier candidate runs failed: the original five regression checks had four
failures and one error; a pre-existing failure was cleared by a delayed
callback; scenario commands used the wrong directory or omitted the required
test database; fresh frontend and hosted environments lacked dependencies;
two frontend suites and the profile production-studio test had assertion
failures; a new negative-test assertion and Ruff formatting check also failed.
The fresh Docker isolation attempt using the default PyPI index failed before
running tests because the package download hit a TLS handshake failure; the
mirror-backed result above is a separate run.
An extra root-level Ruff invocation did not apply the generated project's
path-relative adapter ignores; the CI-style generated-directory lint and
format checks pass. An initial shorter HTTPS timeout probe did not establish
that its server handler was reached and is inconclusive. Corrected runs are
reported separately above. The previous
default-Windows-Proactor backend run remains recorded as failed; the scoped
startup correction above does not relabel it. The real-provider test remains
skipped. Historical
[CI run 45487881616](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45487881616)
passed all eight jobs for `8c2a8c909b27b23802b4ee71450e82a5ebfcd2e7`, not
this candidate; [run 45496167774](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45496167774)
passed at `174eca3d9a6b02f5fe4d42f3e2ae4a360639d5c8`, before these changes.

Next: review exact-head CI and establish an independently administered
builder/policy and fresh deployment observer before any Azure rollout. Verify
a firewall-preserving application path for migration
`0004_order_resolution_hosted_response_outcomes.sql` and
`0005_order_resolution_hosted_start_claim.sql`. Native hosted recovery,
later background failures, HTTP 429 replay safety and live identity remain
unverified; correlation metadata is not independent telemetry.

## Deployment-provenance preflight above PR #61

**Status: In Progress; deployment provenance remains blocked.** The
[copied advisory preflight](../blueprints/maf/workflow/docs/build-attestations.md)
requires an independently administered external policy and verifies three
exact OCI attestations through GitHub CLI. It matches the source and signer
identities and commits, numeric repository IDs, GitHub-hosted runner, standard
SLSA predicate, invocation, and exact subject name/digest in the same verified
result. It rejects malformed, mismatched and ambiguous evidence. A genuine
public GitHub-signed OCI attestation passed locally with `gh` 2.103.3; changing
the independently pinned repository ID failed. This was not a target image.
Synthetic unit tests cover the three-subject control flow and adversarial
mutations, not cryptographic verification.

The policy path alone does not establish independent administration. The
current local-context ACA builds and Foundry ZIP `remote_build` lack a trusted
source-to-built-image binding; no independent observer binds a live
revision/route/identity to these subjects. The preflight does not authenticate
the policy or verifier, inspect Azure, or authorize release. The existing
pre-OIDC failure-injection hard stop is unchanged. Next: independently
administer the trust policy and producer, establish exact checkout/input/output
binding and fresh independently controlled deployment observation, and verify
target isolation before any separately authorized rollout. Do not infer this
from synthetic tests or the public fixture.

## Hosted interruption evidence

**Status: Blocked.** A database read and clearing local flags cannot prove
native hosted continuation. The interruption scenario now blocks before any
adapter call; the live adapter refuses interruption and reconciliation and
keeps unresolved markers. Focused synthetic checks cover the refusal, not live
Foundry recovery. Next: verify native continuation and durable outcome evidence
independently before enabling the scenario. See
[cloud readiness](azure-foundry/readiness.md).

## Live acceptance credential boundary

**Status: In Progress.** Acceptance: require an independently configured HTTPS
origin before reading authentication; prevent bearer redirects and restrict
browser storage injection to that origin without weakening live assertions.
The model endpoint has a separate authorized HTTPS origin and redirect block.
The hosted Responses client and frontend API/stream fetches reject redirects;
ambiguous hosted creates remain unknown. Synthetic checks do not attest a
deployed endpoint, trusted factory, proxy, or real credential handling.
Synthetic checks cover the source and independently generated Order Resolution
profile; no live Entra or Azure call is evidence. Existing local browser suites
remain intact. Exact-head CI and a trusted configured origin remain unverified.
Next: review exact-head CI and independently authorize the live origin.
See [cloud readiness](azure-foundry/readiness.md) for configuration and limits.

## Hosted approval UI repair in PR #62

**Status: In Progress.** Based on `19e1837e2cb4d0781aa34ec7e345c5fed30b7a03`.
The generated Order Resolution API returns the selected host's decision channel
only alongside a pending handle; the UI binds that value instead of assuming
the local channel. The studio refreshes incomplete cases with authorized
reads, retries timed-out and transient refreshes, discards stale results, and
clears the case on authorization failure or sign-out. Source frontend: 59
tests; independently generated profile: 64 tests, build, CSP and three
Chromium origin checks. The isolated repository suite passed 114 tests with
two adapter-selection skips. A generated profile passed local automatic and
human-approval API/MAF/PostgreSQL happy paths and an Agent A loopback
composition with synthetic identities and a Foundry fixture. These are not a
deployed hosted agent or live identity evidence.

A default-Windows-Proactor run of the full generated backend suite failed
three of 251 tests: two Psycopg async errors and a stream 503 instead of 200;
one real-provider test was skipped. This remains a failed check, not a pass.
A separate Windows Selector-policy run completed 251 tests with the same
real-provider skip. All nine canonical scenario cases and their nine contract
test methods passed separately using the generated local API/MAF/PostgreSQL
adapter. No real-provider or deployed hosted-agent evidence is implied.

The generated profile's signed-out Chromium check initially failed at
`1591e20293bbfad351f54243f74fb471203bc274` because it inherited the base
title expectation. The profile now supplies its own title expectation; the
updated generated profile and unchanged base each passed that browser check
locally. CI is configured to exercise both independently generated frontends.
Next: verify exact-head CI and separately establish authorized live approval,
rejection, restart and recovery after provenance and isolation prerequisites.
No Azure resource or production-readiness validation is claimed.

## Acceptance harness contract repairs in PR #62

**Status: In Progress.** Starting revision: `19e1837e2cb4d0781aa34ec7e345c5fed30b7a03`.
The generated profile factory accepts the runner's target metadata and uses its
failure-auth setting. Hosted interruption remains blocked and does not use the
hosted-root setting. Failure evidence checks HTTP correlation
coverage by case, not by comparing HTTP request IDs to approval handles. The
live browser selectors match both the base and Order Resolution labels and read
the case ID from the form. Focused source runner tests and independently
generated backend and UI tests pass; the generated frontend build succeeds.
These are local fixture checks, not Azure evidence.

The recovery-evidence and token-safety fixes are integrated in the
[draft](https://github.com/ppenumatsa1/agent-blueprints/pull/62). Next: review
exact-head checks. Native interruption, reconciliation, deployment, actual
identities and live browser behavior remain unverified; the existing
failure-injection provenance hard stop remains in place.

## Fixed offline synthetic manual tests above PR #61

**Status: In Progress (local implementation and checks completed; draft/CI
review pending).** Verified parent:
`a78854c5fff4d4f518e9fea729d0bba0123ce2bb`.

| Acceptance criterion | Evidence and limitations |
| --- | --- |
| Shipped native execution, not a callback or fabricated result | `scripts/run_synthetic_manual_test.py` in the blueprint builds a dedicated image and runs the canonical MAF approval graph. Both native suspension/response decisions are checked against exactly one in-memory synthetic record. No application factory, business action, model, database or checkpoint is loaded. |
| Enforced boundary and negative checks | Actual Docker inspection gates start on network none, read-only root, UID/GID 65534, capability drop, no-new-privileges, no user mounts/devices/ports/credential environment and bounded resources. In-container denied external/metadata TCP and filesystem writes, capability/privilege/seccomp checks pass. Six actual altered container configurations are rejected before start. Eight unit tests cover capability/resource mutations, allowlisted context, symlinks, remote endpoints, credential exclusion and failure/timeout cleanup. |
| Independent instantiation | Three real-Docker tests pass in source, independent base and independent Order Resolution projects (nine executions total), and both generated CLIs pass approval/rejection. Generated images are built exclusively from their copied allowlists; no original-repository mounts or runtime imports. CI additionally makes the source checkout unavailable for generated checks. The profile's business workflow is intentionally not tested. |
| Regression evidence | Isolated repository suite: 114 tests, two inherited adapter-selection skips; new scripts pass Ruff 0.14.13 lint/format and `git diff --check`. Linux Docker 29.9.3 was used locally through Windows named-pipe transport. Default package-download TLS failed locally; a public HTTPS package mirror passed with unchanged lock hashes and TLS checks. Exact-head CI is pending, not inferred from local results. |
| Preserved controls and limits | Production authorization/separation of duties and disabled browser callbacks are unchanged. Fixed operator-only synthetic execution is implemented, **not** UI dispatch, a same-identity exception, atomic exception audit, domain-specific testing, durable recovery, Azure isolation or production readiness. The host/daemon/source/dependencies remain trusted; container escape resistance against arbitrary hostile code and immutable build provenance are not claimed. |

Next action: review the stacked draft and exact-head CI. Keep all drafts
unmerged; any browser integration or approval exception requires a separate
verified boundary. See the [operator guide](../blueprints/maf/workflow/docs/offline-synthetic-tests.md).

## Polling fallback containment above PR #60

**Status: In Progress.** Parent head:
`99b4303a209c983ca7d306fd6d23473476e85ff6`. Local PostgreSQL tests reproduce
shared-pool starvation without read admission and exercise bounded synchronous
GET admission, repeated stalls, fail-closed 503s, cancellation of a waiter,
real worker completion, business submission and rejection. The generated Order
Resolution path is also exercised. The limit is per store and at most four.
At the supported minimum pool size of two, one read is admitted for
compatibility; one stalled read can leave too few connections for the standard
business workflow. A local reproduction showed a submission timeout while a
simulated stall held a pool connection. At sizes of three or more, the limit
leaves two pool slots outside polling, but they are not reserved against other
traffic. Configure at least three for that limited protection.

On local PostgreSQL 17.12, the minimum-size correction passes six focused
source tests, six in an independently generated base project, and nine in an
independently generated Order Resolution project; both generated Ruff checks
pass. These include healthy minimum-size reads, the single-slot boundary and
release, and size-four business continuity. On the preceding head, full source
and independent base suites passed 168 each, and the independent profile
passed 235 with one real-provider opt-in skip, using the Windows selector
event loop; instantiation tests passed 8/8. Default Windows Proactor runs
failed in all three suites (each two Psycopg async errors and one stream
assertion failure); the selector reruns do not erase those failures. This does
not terminate stalled threads, guarantee business availability under other
traffic, or prove custom adapters, managed identity or network black-hole
recovery. Exact-head CI is pending.

Next action: review the draft and its exact-head CI; separately address bounded
I/O, authentication stalls, network recovery and production capacity.

## Remediation above PR #54

**Status: In Progress.** This work starts at PR #54 head
`11b4bb04c92626fddc3a50b135a8a6d0e379d52a`. Independent validation and
exact-head CI are required before drawing conclusions. Broad public
PostgreSQL firewall access remains a **HIGH production blocker**, tracked in
[#56](https://github.com/ppenumatsa1/agent-blueprints/issues/56). Firewall
changes are not authorized; deployment is conditional on exact-head tests
and verified safe target, isolation, permissions, and provenance.

| Acceptance criterion | Evidence and limitations |
| --- | --- |
| Same-identity development approval | **Blocked.** Same-user approval remains denied, including at the effect boundary. The synthetic adapter uses configured PostgreSQL; the runtime cannot verify isolation of storage, credentials, permissions, or network access. A flag or adapter declaration cannot establish that isolation. Independently verified isolation, trusted deployment provenance, and an atomic exception audit are prerequisites. |
| Manual test safety | The studio does not execute application-supplied manual-test callbacks, even in development. This is an interim control, not an isolated synthetic execution capability. Trusted profile code itself is not sandboxed; an audited fixed test path and its execution boundary require separate design and verification. |
| Stream availability | **Mitigated, not production verified.** SSE uses at most four cancellable async operations/32 streams per process, async bounded HTTPS key reads, and separate read-only PostgreSQL connections with five-second connection/statement/lock deadlines. It no longer submits synchronous work to an SSE executor or borrows the API pool. Tests cover actual locked-read cancellation/connection cleanup, HTTP cleanup, capacity recovery, token expiry and policy revocation. Custom components, managed-identity database credentials, and Order Resolution fall back to authorized polling. Library DNS resolver shutdown and TLS/network-black-hole recovery remain unverified. Polling is synchronous; its admission containment and remaining limits are recorded above. I/O deadlines remain **blocked**. The UI does not indicate polling mode. |
| Rollout and live acceptance | The manual workflow verifies exact successful CI/deployment run heads and a configured deployment-workflow path, checks the active-revision artifact, and defaults destructive injection off. Failure injection has a deliberate pre-OIDC hard stop because source-to-image/hosted deployment provenance is not independently attested; its Azure login and adapter steps are unreachable. The dedicated synthetic environment, scoped identity/RBAC, and reviewed adapter remain unverified. No in-repository workflow currently produces the deployment artifact; the producer path is unset. Firewall rules are unchanged; parent preflight still reports isolation and delegated consent unverified. No rollout or live acceptance is claimed. |
| Local checks | Successor 2026-11-24: isolated repository 105 tests/two adapter-selection skips; complete source and independent base backend discovery 162 each/no skips; independent profile backend 228/one real-provider opt-in skip; generated Agent A 63/no skips. Disposable PostgreSQL and explicit generated Agent A selection were used. Generated base verification 52/no skips; profile canonical contract 9/no skips. Source/base/profile frontend 54/54/56 plus builds/CSP; source and generated base offline browser suites 1 local + 5 history/optional/protocol/activity + 1 production studio each. No live calls. Builds retain >500 kB chunk warnings and backend fixtures emit non-fatal open synchronous-connection ResourceWarnings. |
| Follow-on verification | Successor is based on verified `766d8e46c13447deb10a9a1903e12af296163818`. Generated-profile formatting uses locked Ruff 0.14.13 with the generated 100-column configuration. Source/base CI now use full discovery and generated browser CI uses all three offline suites. Exact-head CI is tracked on the successor draft PR; [historical run 45309564583](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45309564583) at `b7004af4316a419f7b5afd0048a388e9c2af9705` remains failed, not reclassified. The hosted failure runner validates HTTP status, hosted metadata, and exact synthetic-nonproduction target identity for the App Insights consumer; no live telemetry or failure injection is verified. |
| E2E behavior and manual execution | Protected `e2e/local.spec.ts` and `e2e/live.spec.ts` are unchanged. Optional-adapters Chromium coverage exercises evidence display, projection-failure isolation, ordinary approval, and non-execution of legacy callbacks. It does not complete isolated synthetic execution; that capability remains **not implemented**. |
| Other review gaps | Lost-ack tests use a supplied remote ID; an operational source and verification of that ID remain unproven. Acceptance fault controls default off and require operator authorization and revision binding, but have no enforced non-production environment boundary. |
| Independent review correction | The initial read-only review found repeated JWKS fetching on every heartbeat. A five-minute per-application identity cache, single in-flight fetch, 30-second unknown-key/failure refresh throttle, and pre-I/O malformed-header rejection replace that behavior. Expired keys are not a failure fallback. Regression coverage exercises cache reuse, rotation, expiry, failure backoff, concurrent fetch rejection, and cancellation recovery. The independent read-only follow-up found no actionable issue in that correction and retained the disclosed reliability limitations. |

Next action: inspect independent review and exact-head successor CI, retain
both drafts, and separately establish bounded polling/network recovery and
verified isolation before considering any same-identity exception. Retain
production separation of duties, issue #56, and the production-readiness block.

## UX stack Layer 5: read-only protocol context

**Status: In Progress.** Stacked on PR #53 head
`3bdf2646095383583445e0cea04d34d0658c694f`.

| Acceptance criterion | Evidence and limitations |
| --- | --- |
| Explicit, limited context | Each installed adapter requires a click for a selected authorized case. Only a validated status enum is provided; a consumer may transmit it on a later agent run. No workflow client, IDs, payload, prompt, output, or tool contents are provided. |
| Protocol boundary | AG-UI `Context` input and CopilotKit v2 context hook integration points only; no agent run, events, tools, mutations, or protocol-conformance claim. Trusted adapter code is not sandboxed; cleanup cannot be enforced. |
| Failure isolation and accessibility | Focused synthetic unit/axe, failure, and browser checks pass; adapters cannot be sandboxed and cleanup can fail. |
| Independence and evidence | Default dependencies contain no optional protocol packages. A separate local check type-checks and exercises AG-UI core 1.0.4's schema and CopilotKit React core 2.0.0-rc.53's actual hook against a synthetic consumer; no real provider or remote service is verified. Clean generated base/profile and exact-head CI remain pending; preserved local/live E2E specs must remain unchanged. |

Next action: complete validation and open a stacked draft, without merging or
deploying. The inherited profile telemetry fixture mismatch remains disclosed.

## UX stack Layer 4: optional studio adapters

**Status: In Progress.** Stacked on PR #52 head
`f16a4f504f3a80f98819a8750058cabf6778559d`; draft and exact-head CI pending.

| Acceptance criterion | Evidence and limits |
| --- | --- |
| Safe evidence | An optional typed profile projection displays text only for an already selected authorized case. The application must explicitly allowlist safe values; the UI neither fetches evidence nor verifies the projection's privacy. |
| Synthetic manual tests | Superseded by the remediation above: callback execution is disabled in all environments because the browser cannot enforce isolation from real effects. |
| Isolation | Missing, disabled, throwing, or failed adapters leave the base workflow usable; focused adapter and accessibility tests cover these boundaries. |
| Standalone and browser | Browser and independently generated build/test checks are pending. Existing protected local/live specs remain unchanged. |

Next action: finish generated-project and exact-head CI verification; do not
merge or deploy. The inherited profile telemetry fixture mismatch remains
unmodified and broader profile backend success is not claimed.

## UX stack Layer 3: live activity

**Status: In Progress.** This work is rebased on PR #51 head
`14a709e0f682db3776e92ed9cdc194369fecaf47`; the stacked draft and its
exact-head CI remain pending.

| Acceptance criterion | Evidence and limits |
| --- | --- |
| Privacy and authorization | Stream ticks revalidate the token and case policy; only a fixed refresh and heartbeat are emitted. Security tests cover unauthenticated, denied, revoked and invalid-cursor requests. |
| Late commits and replay | PostgreSQL 17 late-commit test shows a fresh authorized snapshot includes an older late commit. Browser reconciliation replaces snapshots and does not infer a commit watermark; concurrent inserts may need another scan. |
| Lifecycle and failure | Case/account cleanup aborts requests and stops waiting for token acquisition. Streams end after 30 seconds; refresh plus 20 seconds of sustained connection resets the failure budget. Three short or failed attempts lead to reauthorized polling. Scans start at most every 15 seconds and cap at 50 pages/60 seconds; overflow is explicitly shown in the UI. |
| Local and generated verification | Rebased focused UI tests (33), build, both history/browser specs, and six stream-security tests pass. Before rebase, fresh independent base/profile UI suites passed 38/40 tests, builds and browser specs; their CI-selected PostgreSQL backend suites passed 128/177 tests (one profile opt-in skip). Isolated repository suite passed 105 tests with two documented skips; full exact-parent revalidation remains pending. |

Inherited Layer 2 profile telemetry fixture mismatch remains disclosed and
unchanged. No cloud changes or later adapters are included. **Next action:**
open the stacked draft, finish generated and exact-head checks, and keep merge
disabled. The stream deadline cannot cancel a stalled synchronous database or
identity worker, which can retain a pooled connection until it returns; see
the bounded remediation and polling limitation above.

## UX stack Layer 1 acceptance

**Status: implemented locally; stacked draft PR and exact-head CI pending.**
This layer is frontend-only and depends on the frozen PR #49 snapshot
`57794230845939471c00fc2e7994815492bc9ada`.

| Acceptance criterion | Scoped evidence |
| --- | --- |
| Generic generation-time profile boundary | `WorkflowStudioProfile` owns title, description, labels, disabled capability flags, payload projection/rendering, and optional decision binding; the default profile contains no order/refund/shipment/customer vocabulary |
| Reusable workflow studio components | `StudioShell`, `RequestComposer`, `CaseSummaryPanel`, `ApprovalPanel`, and `CaseMetadataPanel` adapt the existing `WorkflowCase`/`WorkflowClient` without changing protected endpoints or auth semantics |
| Security and recovery preservation | Focused tests cover signed-out behavior, submit/open, approve/reject, reviewer UUID validation, idempotency reuse after failure, scoped client behavior, recovery/failure visibility, account isolation, and axe checks |
| Later layers remain disabled | History, live activity, evidence, manual tests, AG-UI, and CopilotKit render only as `Not enabled`; no later-layer runtime was added |
| Generated independence and browser boundary | Focused instantiation verifies copied profile/component/test/browser files and rejects source references to `agent-blueprints` or `maf-monorepo`; a new production-build Chromium spec passes while PR #49's existing local/live specs remain byte-unchanged |
| Local validation | Base frontend 12 tests pass; fresh profiled generation 14 tests pass; base/generated production builds, base CSP, preserved local Chromium, new production-build Chromium, focused instantiation, and the required 105-test repository suite with two documented adapter-selection skips pass without Azure credentials |

**Next action:** open the Layer 1 draft PR against
`ppenumatsa1-integrate-azure-foundry-fleet`, require exact-head CI, and keep
history/activity/evidence/manual-test/AG-UI/CopilotKit work in future stacked
layers. No backend/cloud change or production readiness is claimed.

## UX stack Layer 2 acceptance

**Status: implemented; draft PR #51 is open above Layer 1 PR #50, and the
authorization/pagination correction is locally verified. Exact-head CI is
green for the bounded-scan revision.** This is a separate draft stacked above
Layer 1 PR #50 (`ppenumatsa1-ux-layer-1-studio-shell`), not a merge or
deployment.

| Acceptance criterion | Local evidence |
| --- | --- |
| PostgreSQL-backed case history | Existing `wf_cases`; fixed SQL tenant plus owner/reviewer predicates and status filtering select keyset candidates. The configured `AccessPolicy.authorize_read` is applied before public pagination; at most 1,000 candidates are checked over 10 batches of at most 100 per request. If more candidates remain before the authorized page is complete, the API returns a generic 503 with no partial items or cursor, never silently dropping permitted records. The stricter-policy regression verifies denied owner/reviewer rows, cursor position, deny-all metadata, and 1,000-candidate exhaustion. Six focused PostgreSQL history/security tests and all 136 backend tests pass. |
| Durable activity | Committed `wf_audit` only, fixed safe event mapping, unknown events excluded; no payload, actor, request/checkpoint ID, prompt, model output, or tool content. Event mapping/privacy coverage passes; native MAF continuation remains separate. |
| Contract safety | Versioned API response schemas, bounded page size/cursors, and frontend runtime validation. Existing single-case and decision APIs remain compatible. |
| Reusable studio UI | Generic profile-driven sidebar and timeline support status filter, refresh, keyset paging, loading/empty/error states, and stale-response suppression. Each new request generation resets `loadingMore`; deferred-load tests cover history-filter changes and activity-case switches, including the re-enabled load-more control. Frontend unit tests include axe checks. |
| Independent generation | Base and Order Resolution outputs previously passed verification suites (52 and 61 tests), frontend suites (19 and 21 tests), builds, and separate history/studio browser specs. The generated Order Resolution hosted-agent suite passed 63 tests. Its PostgreSQL backend suite ran 190 tests with two explicit skips and one unrelated pre-existing failure in `test_live_client_uses_response_correlation_id_for_telemetry_pair` (telemetry includes an extra `http_status` field). These local results predate the current correction; exact-head CI run [45294440225](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45294440225) passed all seven jobs at `bfcbe1e6ee31945942c45422799374ddb026aeb1`, including generated validation. PR #49 `local.spec.ts` and `live.spec.ts` remain byte-for-byte unchanged against the parent. |
| Verification | Current source: six focused PostgreSQL/API-security tests and all 136 backend tests pass; frontend 21 tests, production build, CSP check, and history/studio browser specs pass. Repository `python -m unittest discover -s tests -v` passes 105 tests in an isolated environment with `requirements-dev.txt` (two documented adapter-selection skips). Vite reports the existing >500 kB chunk warning. Exact-head CI run [45294440225](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45294440225) passed all seven jobs on `bfcbe1e6ee31945942c45422799374ddb026aeb1`. |

No evidence, manual-test, streaming, AG-UI, CopilotKit, or optional adapter
work is included. No Azure resource or firewall change is authorized or
claimed. **Next action:** obtain human review of PR #51; disclose the inherited
local Order Resolution telemetry test failure. Do not merge or enable
auto-merge.

PR #17 merged into `main` at
`0c1297cc8e93c62f69d61d0eb3bdabf3c27c683d`, with parents
`de1cbe4cc3a93f2473a6f8f5f9e063d1ae278fa3` and final #17 head
`1a3e7c75f2ff5ffa8ef055e474a7ea5fb6d2a397`. The merge tree
`f4623d919f75ec4f6d5bf2d9f4e365a1bdcaa124` matches the PR #17 head tree.
Exact-main run
[45027884271](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45027884271)
passed all six jobs for that historical baseline. PRs #36, #37 and #40 are
merged into current `main` at
`49932ee0cd61ee653a5f86be0f43873cec197ff9`; that exact main revision is the
base for the #39 evaluation follow-on. Green CI is not blueprint completion,
release readiness, or Azure deployment approval.

## Local Azure/Foundry integration acceptance

**Status: Completed for local integration; Azure API/web runtime and database
connectivity verified; hosted business execution and production unverified.**
The integration starts at exact main
`886b628fdea02f9089c385b4ed0fc46d90f375e8`. Accepted sources are
A `708a4185abe149526c606477de02cd57c5d90a9c` (#45),
C `722fc4e32937df4bd94678ec12380cac2a7c84df` (#48; runtime TLS fix
`509fb0b20c80fa8e436de4ac782f618c47f38bd3`),
B `b09877c219d3b9ec813614d879f5e1897729b254` (#47), and
D `9336176459cf38c367c8956849ceac32ffa98cbc` (#46).
Their exact-head owner CI is green. Runtime integration revision
`920a339777e23be85c34402afb7fb4322ca26e02` supplies the following
local evidence. Later owner follow-ups record TLS/provenance evidence and
enforce image-owned CA configuration in the generated-image guard; application
runtime bytes are unchanged.

| Acceptance criterion | Scoped local evidence |
| --- | --- |
| Native MAF and separate hosted/business persistence | Source backend 124 pass; fresh generated backend 169 pass, one explicit real-provider opt-in skip; hosted 41 and publisher 9 pass |
| Authenticated human prebinding, terminal replay, one effect, null hosted checkpoint columns | Isolated PostgreSQL 17 authority/composed-wire suite 13 pass; terminal retries do not redispatch Responses |
| Exact business contract and generated independence | Generated verification 61 pass without skips, including both actual adapters and all ORS-001..009; root 87 pass with two disclosed adapter-not-selected skips |
| Canonical protected API image and system trust | Backend-only production image/import/composition guard passes; normal hosted `app.main` Docker command/lifespan reaches health `204` and protected `401`; actual PostgreSQL TLS confirmed; wrong hostname and untrusted CA rejected |
| Local stack, frontend, infrastructure, and evidence boundaries | Compose API/web/PostgreSQL healthy; source/generated UI 9/10 pass, builds/CSP pass, Chromium render passes; infrastructure 17 plus base 9 pass and Bicep compilation/lint pass; generated Ruff 87 files pass; evidence keeps cloud/production unverified and release blocked |

Builds use supported credentialless HTTPS `PYTHON_PACKAGE_INDEX` and
`NPM_REGISTRY` overrides without disabling TLS, hashes, or lockfile integrity.
Synthetic certificate trust is confined to disposable test containers;
deployment must not override image-owned `SSL_CERT_FILE`. Existing test
connection ResourceWarnings and the Vite chunk-size warning remain disclosed,
not waived production checks. Harness import-path/database setup failures were
corrected before the final complete suites passed; no tests were removed.

**Next action:** draft PR #49 now includes the generated startup correction at
`2ef516107b47f57ea266021b2651ca13b235bd3e` and the frontend upstream-TLS SNI
correction at `9d5a66315f223cb424b70a20679cd6d950f47ffb`. ACR runs `ch5` and
`cha` produced immutable API and web digests. The sole active revisions
`aborsfoundpv2n45-api--final-2ef5161` and
`aborsfoundpv2n45-web--final-9d5a663` are healthy. Live checks returned API
`/healthz` `204`, unauthenticated `/api/cases` `401`, web root `200`, and
proxied web `/healthz` `204`; API startup logs record successful
managed-identity `database.connect`. The final API binds the active hosted
identity and `Hosted.Workflow.Invoke`, while prohibited local runtime settings
remain absent. No business action was invoked. Preserve this exact revision,
image, endpoint, configuration, and log evidence; then complete only the
separately authorized hosted/browser/evaluation checks. Remove the temporary
broad E2E firewall rule after E2E and replace it with actual API outbound
addresses plus the operator address only if still needed. Production
authorization remains unverified. The original architecture HTML remains
unchanged.

The later observability rollout exposed an independent generated-image
packaging blocker before any replacement was created: the API bridge copied
`bridge.py` and `client.py`, but `client.py` now imports the app-owned
`credentials.py` module. The generator now owns an explicit typed three-file
manifest and validates it against the complete transitive relative-import
graph, rejecting both missing and unrelated sibling modules. Focused generator
and infrastructure contracts pass 17 tests, the independently generated
PostgreSQL 17 selection passes 164 tests, and the normal backend-only image
build imports `bridge`, `client`, and `credentials` from one image package
before composing `ResponsesWorkflowHost`. This is source/package evidence, not
new cloud acceptance. Deployment may resume only from a green exact-head run
and in a separately authorized immutable rollout that replaces the failed
revision.

## Hosted durability correction checkpoint

**Status: local correction passed; deployment remains blocked.** The hosted
pending transition and native decision-handle binding now commit atomically
with the hosted binding and audit event. The replay path verifies or repairs
the exact handle/channel under the same row locks, so a binding failure cannot
strand a pending proposal. The Responses client also obtains authorization
before claiming a fresh durable operation: token failure sends no POST and
leaves no claim, while ambiguity after a possible send remains fail-closed.

Evidence passed locally: two focused PostgreSQL regressions, 63 source hosted
tests, 166 independently generated PostgreSQL/backend tests with one explicit
provider-opt-in skip, 63 generated hosted tests, nine canonical ORS contract
tests without skips, 105 repository contract/readiness tests with two
documented adapter-selection skips, and generated/source Ruff checks. No cloud,
workflow, database, RBAC, firewall, or network state changed. Require green
exact-head CI before any separately authorized immutable deployment.

## Immutable deployment and signal checkpoint

**Status: Azure runtime deployment and the bounded version-9 signal comparison
passed; production release remains blocked.** Exact source
`a302e939810283bce47867b8fa088374f3d204ad` passed all seven PR #49 jobs in
[run 45275635199](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45275635199).
The separately authorized rollout published active hosted
`order-resolution:9` and API revision
`aborsfoundpv2n45-api--a302e939`. The API image is pinned to
`sha256:6991536d9cf23efd9bdf1b21a94d1c9bddaa245a151d4b709a13235905eebf79`;
the unchanged web revision `aborsfoundpv2n45-web--0000002` remains pinned to
`sha256:f8a43d68c38707a61ab60b673401427d0c7266d1ebb3dde04a602c07bf3a9ce7`.
Deployment verification passed 32/32 checks: API health `204`, protected
unauthenticated request `401`, web root `200`, web health `204`, and API-UAMI
PostgreSQL login with `sslmode=verify-full`, TLS 1.3, and system trust.

The bounded comparison invoked exactly two synthetic cases. The automatic case
completed with one PostgreSQL synthetic effect and zero real or external
effects. The second case remains durably pending HITL with no decision, claim,
effect, terminal event, approval, rejection, or resume. Version-9 evidence
passed 16/16 checks: spans changed from 276 to 243, API spans from 74 to 26,
hosted spans from 202 to 217, pooled-borrow `database.connect` spans from 52
to zero, MSI token spans from 54 to 52, and Foundry data-plane dependencies
remained 128. Physical database-open visibility remained, stable privacy-safe
workflow stages were present, and exporter failures, optional A365 startup
exceptions, raw-content rows, and payload markers were all zero.

**Unresolved next actions:** obtain a distinct delegated reviewer and execute
the authorized HITL resume/link proof without weakening reviewer separation.
PostgreSQL firewall hardening is deferred. Retained read-only evidence shows
the broad `temporary-e2e-public-remove-after-e2e` rule plus five narrow
Container Apps rules, while the environment advertises 407 possible outbound
addresses. The repository supports a temporary exact-IP operator rule in
`scripts/azure/migrate.ps1`, but no replacement API and operator path has been
validated with the broad rule absent. No firewall or network change was made.
PR #49 remains draft, open, and unmerged.

## Azure/Foundry Workstream C

**Status: In Progress.** The cloud application increment adds an SDK-free
hosted-workflow port, explicit `local` versus `hosted` composition, API-UAMI
caller tokens, Azure PostgreSQL managed-identity/password configuration,
verified TLS requirements, bounded connections, explicit runtime/migration
identity separation, and restart reconciliation for ambiguous hosted outcomes.
The API UAMI is the sole PostgreSQL runtime principal. The hosted identity
calls the protected `/api/internal/hosted/v1` boundary with the fixed
`Hosted.Workflow.Invoke` app role and receives no database configuration.
Durable case/conversation/channel binding, case-bound idempotency, exact
Agent A operation-journal conversion, and business-only hosted
pending/decision/effect/completion state leave local checkpoint columns null.

Acceptance evidence is local only: 117 source-backend tests, 117 tests in a
fresh generated generic backend, 159 tests in a fresh generated Order
Resolution backend, the ORS-001..009 adapter contract (9/9), 68 root tests
with two expected unselected-adapter skips, and source/generated frontend
suites with 9/9 or 10/10 tests plus build/CSP passed. A PostgreSQL 17 and
loopback HTTP test composes Agent A's live `HttpHostedBusinessStore` and
`ResponsesClient` with C's exact journal types, covers restart/duplicate
no-replay with changing opaque platform call IDs, revocation and changed-intent
negatives, post-terminal approved/rejected command replay through Agent A's
acknowledged journal without a second Responses dispatch, and one
decision/effect with null checkpoint fields.
Fresh generated Compose built through approved package proxies, ran explicit
migrations, became healthy, and returned root `200`, health `204`, and
protected API `401`. The canonical backend image also exports
`SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt` so bundled libpq/OpenSSL
discovers the same readable system bundle selected by
`PGSSLROOTCERT=system`; `verify-full` remains mandatory. An isolated
PostgreSQL 17 image proof passed normal `app.main` startup and reported TLS in
`pg_stat_ssl`; a trusted certificate for the wrong hostname and an untrusted
CA both failed certificate verification. The
[application security contract](azure-foundry/application-security.md)
records the identity matrix, Agent A interface, Agent B outputs, OBO decision,
and recovery behavior. Draft PR [#48](https://github.com/ppenumatsa1/agent-blueprints/pull/48)
contains the Workstream C implementation. Next action: obtain draft-PR review
and exact-head CI,
then run the listed live-only checks after integration and authorized
deployment. No Azure resource or live RBAC/configuration was changed here.

The TCP-readiness correction from [#38](https://github.com/ppenumatsa1/agent-blueprints/issues/38)
and current MAF-native patterns are in merged #37. PR #39 is being reconciled
directly onto current `main` without replaying #37. Its new exact-head
validation is required; earlier stacked-branch CI does not validate this
baseline.

## Azure/Foundry Workstream B

**Status: In Progress - ready for independent validation, not deployed.**

Starting from exact main
`886b628fdea02f9089c385b4ed0fc46d90f375e8`, Workstream B adds the
[deployment plan](../.azure/deployment-plan.md), infrastructure-only azd
descriptor, modular public-network Bicep, Azure CLI deployment orchestration,
infrastructure contract
tests, and the [operator evidence](azure-foundry/infrastructure.md). East US 2
is selected without a split-region design for `gpt-4.1-mini`
`2025-04-14` on `GlobalStandard` capacity 10. Read-only evidence found enough
model quota/capacity and dependent-service quota. Azure CLI mode validates the
authorized active context and reports the unrelated azd mismatch without
blocking; explicit azd mode still fails closed.

Acceptance evidence: Bicep build/lint and 17 infrastructure contracts pass; the
root suite passes 68 tests with two expected adapter-selection skips; all new
PowerShell/Python files parse. No Azure resource, RBAC assignment, database
principal, migration, deployment, rollback, or teardown was executed.
Deployment generates an independent Order Resolution project, requires the
Agent A/C hosted and managed-identity interfaces, patches only the generated
nginx upstream to the exact API FQDN, and prohibits the source blueprint,
synthetic application selector, local workflow host, and file checkpoints.
The protected API state boundary and API-only PostgreSQL access are established
before publication. The pending hosted identity receives only a dedicated API
application role before the same journaled version is required active; hosted
code receives no direct database access. Agent Consumer assignment additionally
uses only the official exact agent scope derived from validated project output
and the fixed publisher agent name; wider or another-agent scopes fail closed.
The hosted app role authenticates service identity only; API-owned exact
human principal/case authority bound to the server-selected conversation and
channel must exist before Responses dispatch and cannot be inferred from the
hosted token. Foundry user/session/call values are opaque platform correlation,
not human authority; no caller-selected session or actor metadata is sent.
Exact final A `708a4185` plus final C `722fc4e3` (all-six CI run
`45087843018`) generation produced
byte-identical owned files, built/imported the canonical no-dev backend, and
passed nonconnecting wire composition. The integration coordinator
independently reports default Docker CMD/app lifespan passed against isolated
PostgreSQL 17 with inherited image CA setting, verified TLS, health `204`, and
protected `401`; hostname and trust negatives failed closed. B did not rerun
that suite. The exact generated web target also passed unchanged `npm ci`,
production Vite build, and CSP verification through the credentialless HTTPS
npm proxy. C's TLS code parent `509fb0b2` owns the canonical image
`SSL_CERT_FILE`; B deploy contracts
prohibit overriding the image default. Canonical packaging evidence is
complete.

**Next action:** independently validate the exact PR revision, supply the
deployment-specific hosted endpoint/agent-name/administrator/journal values,
review Azure CLI provider what-if, and approve resource
inventory, cost, identity, and public-network controls before deployment.

## Reconciled engineering backlog

The foundation and the integrated review do not establish blueprint
completion or deployment readiness. The issues below retain their own
acceptance criteria, dependencies and required independent evidence.
Deferred work remains deferred; critical security checks are not waived.
The [issue and fix journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-22---issue-and-fix-status)
records the current review snapshot, scoped evidence, and next actions. Its
open PR references do not imply those changes have merged into this branch.

| Area | Open tracking issues | Next action |
| --- | --- | --- |
| Hosted identity, execution and recovery | [Caller binding #22](https://github.com/ppenumatsa1/agent-blueprints/issues/22), [host and checkpoints #19](https://github.com/ppenumatsa1/agent-blueprints/issues/19), [lost-response recovery #20](https://github.com/ppenumatsa1/agent-blueprints/issues/20), [external effects #32](https://github.com/ppenumatsa1/agent-blueprints/issues/32) | Implement and independently verify the security and durability boundaries. |
| MAF adopter extension patterns | [Reusable model, agent, prompt, tool and executor patterns #35](https://github.com/ppenumatsa1/agent-blueprints/issues/35) | Specify typed framework-native extension contracts and prove each in an independent synthetic generated application. |
| Independent readiness | [Trust and contract approval #21](https://github.com/ppenumatsa1/agent-blueprints/issues/21), [evaluations and browser hints #25](https://github.com/ppenumatsa1/agent-blueprints/issues/25) | Obtain authorized trust and produce actual evidence; retain unverified outcomes. |
| Azure and operations | [Infrastructure #18](https://github.com/ppenumatsa1/agent-blueprints/issues/18), [managed PostgreSQL #24](https://github.com/ppenumatsa1/agent-blueprints/issues/24), [telemetry #26](https://github.com/ppenumatsa1/agent-blueprints/issues/26), [live identity and accessibility #27](https://github.com/ppenumatsa1/agent-blueprints/issues/27), [deployment #28](https://github.com/ppenumatsa1/agent-blueprints/issues/28) | Close offline prerequisites, validate access and obtain approval of the concrete deployment plan before live validation. |
| Developer experience and demonstration | [Cross-platform tooling #23](https://github.com/ppenumatsa1/agent-blueprints/issues/23), [measured local demo #29](https://github.com/ppenumatsa1/agent-blueprints/issues/29) | Verify supported environments and record a representative end-to-end run. |
| P1 reference application and later work | [Permanent standalone reference #30](https://github.com/ppenumatsa1/agent-blueprints/issues/30) is P1 and still requires separate repository authorization; [ACA runtime #31](https://github.com/ppenumatsa1/agent-blueprints/issues/31), [Specification Studio #33](https://github.com/ppenumatsa1/agent-blueprints/issues/33), and [later blueprints #34](https://github.com/ppenumatsa1/agent-blueprints/issues/34) remain separately scoped. | Track the P1 deliverable without creating a repository absent authorization; preserve out-of-phase boundaries for the remaining items. |

The #17 row-level acceptance evidence below remains more detailed. In
particular, #28's offline prerequisites are distinct from authorized live
deployment; deployment is expected to produce evidence for hosted/cloud
issues and need not wait for all live verification to close.

| Requirement or capability | Phase | Status | Acceptance criteria | Evidence or PR | Next action |
| --- | --- | --- | --- | --- | --- |
| Three-repository architecture and boundaries | 0 | Completed | Document Specification Studio, Agent Blueprints, and App/API Blueprints and their handoff. | [Overview](software-factory-overview.md); [PR #1](https://github.com/ppenumatsa1/agent-blueprints/pull/1) | Update architecture when decisions change. |
| Reference analysis, catalog, and engineering standards | 0 | Completed | Document reference evidence, framework-native blueprints, and engineering boundaries without claiming unverified deployments. | [Analysis](reference-repository-analysis.md); [catalog](blueprint-catalog.md); [standards](engineering-standards.md); [PR #1](https://github.com/ppenumatsa1/agent-blueprints/pull/1) | Reassess compatibility as blueprints are implemented. |
| Repository licensing | 0 | Completed | Select and include a license for the public repository. | [MIT License](../LICENSE); [PR #1](https://github.com/ppenumatsa1/agent-blueprints/pull/1) | Retain third-party notices when code is reused. |
| Supplied interactive architecture source | 0 | Completed | Include the original HTML without fabricating a replacement; retain its source bytes and identify it as a historical baseline. | [Original HTML](software-factory.html); [PR #2](https://github.com/ppenumatsa1/agent-blueprints/pull/2) | Preserve the supplied source. |
| Prototype and production readiness contracts | 0 | Completed | Schemas and fixtures preserve per-requirement results, protect critical gates, disclose prototype limitations, and represent reviewed production risk acceptance. | [Policy](readiness-contract.md); [PR #2](https://github.com/ppenumatsa1/agent-blueprints/pull/2) | Independently review scenario contract and trust setup. |
| Living tracker and Phase 1 plan | 0 | Completed | Track status, acceptance criteria, evidence, and next actions; keep work packages independently verifiable. | [Plan](implementation-plan.md); [PR #2](https://github.com/ppenumatsa1/agent-blueprints/pull/2) | Update with each meaningful PR. |
| Cross-framework Order Resolution specification | 0 | Completed | Define a versioned framework-neutral scenario set for triage, policy retrieval, deterministic resolution, authorized human decisions, idempotency, restart recovery, and evaluations while requiring native framework checkpoints and separate application persistence. | [Proposal](order-resolution-specification-proposal.md); merged PR [#40](https://github.com/ppenumatsa1/agent-blueprints/pull/40) is included in current `main`. | Obtain a human readiness decision on the specification, then map it independently to each future framework blueprint with implementation-specific evidence. |
| Executable Order Resolution acceptance contract | 0 | Completed | Encode exactly `order-resolution-spec/0.1.0` and `ORS-001` through `ORS-009`; preserve decimal USD round-half-up refunds, approval/action/outcome rules, explicit evidence failures, and separate business versus technical assertions without adding a runtime. | [Fixture](../scenarios/order-resolution/README.md), [root contract tests](../tests/test_order_resolution_contract.py), and merged [PR #42](https://github.com/ppenumatsa1/agent-blueprints/pull/42). | Framework mappings must preserve its normalized outcomes while adding implementation-specific evidence. |
| Generated MAF Order Resolution application | 1 | In Progress | Preserve default generation; add one explicit independently owned profile using FastAPI, React, PostgreSQL, Compose, native MAF workflow/checkpoints, deterministic proposals, authorized decisions, fail-closed policy evidence, durable synthetic effects, native evaluation, and no source runtime dependency. | Merged [PR #44](https://github.com/ppenumatsa1/agent-blueprints/pull/44) supplies the application and merged [PR #41](https://github.com/ppenumatsa1/agent-blueprints/pull/41) supplies durability/effect safety. Draft [PR #43](https://github.com/ppenumatsa1/agent-blueprints/pull/43) integrates evaluation/readiness. A fresh external generation passed 147 backend tests, 10 frontend tests plus build/CSP, `ORS-001` through `ORS-009` with no skips, native deterministic technical/business evaluations, an unverified independent readiness report, source-independence checks, and Compose root `200`/health `204`/protected API `401`. Native MAF retains checkpoint ownership. | Obtain exact-head six-job CI and independent review. Keep real downstream guarantees unverified/#32-blocked; real model quality, browser evidence, trusted provenance, deployment, and production readiness remain incomplete. |
| MAF modularity foundation and supply-chain guard | 1 | In Progress | Separate sibling backend/frontend contexts and API/lifecycle responsibilities, use canonical imports without compatibility shims, preserve native recovery, reject the compromised `agent-framework` umbrella distribution, verify the approved core wheel against the canonical `uv.lock`, and ensure generated-verifier failures and skips fail CI. | PR #11 merged to `main` as `587e6cc1abc23a67845c8193d486cc65c8b52854`; PR #17 and the approved-wheel guard are included in `main`. The then-current exact-main run [45027884271](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45027884271) passed all six jobs, including source/generated locked installs and rejection tests. Current #37 integration evidence is tracked separately below. | Preserve the canonical lock and hash verification; keep runtime and hosted claims scoped to evidence. |
| Versioned database migrations | 1 | In Progress | Preserve fresh-database creation and safely adopt only an exactly recognized legacy baseline; never stamp unrecognized or later-owned schemas. | Integrated `SPEC-12`, `backend/migrations/baseline.sql`, migration-aware startup and runtime least privilege passed in #17 `maf-core` and `maf-independent` jobs on `b633539` / run 44955776238. Historical PR #16 run and PostgreSQL 16 tests are separate; managed restore/version operations tracked in [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24). | Verify against the selected managed PostgreSQL target and backup/restore operations; do not infer Azure support from local tests. |
| Generated-project documentation | 1 | In Progress | Copy adopter/operator guides and all eight design documents; map requirements to implementation/tests, maintain the evidence journal, distinguish current/planned capability, and verify links/copy inclusion. | Exact-main run [45027884271](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45027884271) passed the generated documentation and link checks after #17 merged. | Keep copied documentation synchronized and preserve the no-readiness boundary. |
| Cross-platform developer experience | 1 | In Progress | Maintain uv-based portable lock, Ruff/format, locked source/generated installs/builds, and usable editor tasks without shared runtime dependencies. | Run [44955776238](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44955776238) passed locked source/generated jobs on `b633539`. Headless generated debugpy/DAP was owner-reported; macOS, Restricted Mode and interactive UI remain unverified. Track [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23). | Verify remaining platform/debugger evidence against a named revision; any tree/base change requires exact-head CI. |
| Privacy-safe observability | 1 | In Progress | Use one supported global provider per runtime, enable native MAF instrumentation only with sensitive/message capture disabled, and verify connected hosted traces rather than row presence. | PR #49 version 5 on `acf2911b76b470d5b7254d97ba2b6934f5444ddb` passed the bounded start-trace gate. Trace `9ff606620c4a4d728da127c531ffef40` has one privacy-safe hook-created `invoke_agent` root, 101 hosted spans, 37 API spans, 193 hosted logs, 136 resolved parent edges, exact conversation/case/version/deployment/Foundry bindings, and zero exporter errors, AppExceptions, raw-content fields, synthetic payload leaks or pending effects. The two unmatched parents are the expected external caller and explicitly marked non-exported AgentServer platform contexts. The verifier now queries dependency roots and validates the two-component distributed forest; focused tooling tests pass. Resume/link proof is still blocked by the distinct reviewer credential. | Obtain the assigned reviewer credential and verify the resume trace plus explicit durable link; retain the start proof and do not infer model/token spans on deterministic execution. |
| Reusable MAF extension patterns (#35) | 1 | In Progress | Demonstrate independently needed application config and authorization around direct MAF `Agent`, `@tool`, `Executor` and `WorkflowBuilder`; retain explicitly versioned prompts and an independent generated fixture. | Merged PR #37 removes redundant `ModelClientFactory`, `AgentDefinition`, `build_chat_agent`, and `ToolRegistry`; direct MAF composition, `ModelSelection`, `PromptAsset`, and request-scoped `ToolAuthorization` remain. Current merged state includes #36's external-effect boundary and #40's Order Resolution proposal. Exact combined-head evidence is recorded in merged PRs and current-main Actions. Arbitrary trusted callbacks remain unsandboxed; absolute non-bypass is unverified. Consequential effects remain restricted by #32. | Keep #35 and hosted capabilities in progress/unverified. |
| MAF evaluation extension (#25) | 1 | In Progress | Define app-owned datasets, rubrics, deterministic checks and thresholds; map native MAF results strictly to selected-contract readiness checks; preserve failed/unverified semantics and source/generated independence without making unsupported quality claims. | Merged PR #39 supplies the mapper without an evaluator framework. Draft [PR #43](https://github.com/ppenumatsa1/agent-blueprints/pull/43) uses native MAF `Evaluator`, `LocalEvaluator`, `@evaluator`, and `evaluate_agent()` in the generated Order Resolution profile. Local deterministic business and technical results pass; the independent validator remains unverified without trusted attestation. | Obtain exact-head CI and human review. Keep #25 open until actual model and browser evaluation evidence and independent provenance exist. |
| Foundry-first infrastructure staging | 1 | In Progress | Stage restrictive Bicep/azd paths without provisioning resources or claiming live connectivity. | Exact #17 run [44960731511](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44960731511) passed `maf-infrastructure` and generated infrastructure checks on `8b3c357`. Network, identity, cost and Azure behavior remain unverified. | Preserve no-provisioning boundary; infrastructure checks do not establish deployment or live connectivity. |
| Locked developer tooling dependency integration | 1 | In Progress | Keep one canonical uv lock, install source/generated environments reproducibly, lint/format and build independent generated projects. | Integrated lock includes dependencies from #13 and #14; exact #17 `maf-core`/`maf-independent` jobs passed at `b633539` in run 44955776238. Workstream #13 remains independently reviewable; no PR is superseded by aggregate evidence. | Compare feature delta/tree when sequencing merges; see [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23); rerun exact-head CI for later changes. |
| Cross-cutting implementation quality | 1 | In Progress | Before approval, remove shims/forwarders/obsolete paths, duplicate code, unused dependencies and stale config; preserve behavior and update dependent tests, Dockerfiles, CI, docs and generator. | [Acceptance gates](implementation-plan.md#cross-cutting-pr-acceptance-gates); [canonical structure](../blueprints/maf/workflow/docs/design/projectstructure.md); [engineering journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md). | Review remaining cleanup and rerun focused regressions plus exact-revision CI for any resulting tree change. |
| Versioned business database baseline | 1 | In Progress | Explicit schema-owner migration, per-revision drift checks, restricted runtime startup, data preservation, future upgrades and recovery/rollback limits. | [PR #16](https://github.com/ppenumatsa1/agent-blueprints/pull/16), [run 44940559106](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44940559106) passed five jobs for `eb898f6`. Combined source/generated backends passed 68 tests each locally on PG 16.15 and 17.12 at `af3955a`; exact #17 `maf-core` and `maf-independent` checks also passed at `b633539` / run 44955776238. Earlier failures and unverified outcomes remain in the [journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md). | Live restore and hosted identities remain unverified. |
| Combined engineering integration | 1 | In Progress | Run source/generated security, durability, migrations, telemetry, independent acceptance, Compose, UI, and offline IaC together; preserve exact contracts and failed/unverified outcomes. | PR #17 merged into `main` at `0c1297c`; exact-main run [45027884271](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45027884271) passed all six jobs for that historical baseline. The current #37 integration commit `245cbe2` passed all six jobs in exact-head run [45040560075](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45040560075), with GitHub merge-ref/tree verification recorded in the #35 row. | Human review; green CI is not readiness or Azure deployment approval. |
| Synthetic business scenario and approved contract (P1-01) | 1 | In Progress | Approve a non-destructive scenario and exact contract digest, with explicit criticality and profile gates. | [Scenario and golden cases](../scenarios/order-adjustment/README.md); [test-only API adapter](../blueprints/maf/workflow/backend/tests/order_adjustment_adapter.py); independent authorized exact-contract review tracked in [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21). | Obtain and independently administer approval of the exact contract bytes. |
| Normalized evidence and decision inputs (P1-02) | 1 | In Progress | Map test results, artifacts, baseline contracts, and human decisions to explicit IDs and scope. | [Synthetic runner](../blueprints/maf/workflow/backend/tests/evidence_runner.py); [input and trust schemas](../contracts/); [validator tests](../tests/test_readiness.py); independent result provenance in [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21). | Independently administer and protect result attestation and human decisions. |
| Executable readiness validator (P1-03) | 1 | In Progress | Verify traceability, evidence bytes and freshness, criticality, decisions, and profile gates; reject invalid evidence as proof of passing. | [Validator](../readiness/validator.py); [acceptance tests](../tests/test_readiness.py) | Verify trusted provenance, human authority, and repository protection. |
| Readiness CLI and machine-readable report (P1-04) | 1 | Completed | Consume approved inputs, preserve outcomes and disclosures, emit a report, and use profile-appropriate exit codes. | [CLI](../readiness/__main__.py); [tests](../tests/test_readiness.py); unsigned synthetic results produce an unverified report. | Independently administer trust and result provenance. |
| Local development stack (P1-05) | 1 | In Progress | Start React, FastAPI, PostgreSQL, and Docker Compose; automated tests need no Azure credentials, while interactive sign-in uses existing Entra configuration. | [Blueprint](../blueprints/maf/workflow/README.md); source/generated Compose checks passed in exact-head run 44955776238 (UI 200, health 204, protected API 401, private checkpoint volume). | Verify interactive Entra and accessibility under [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27). |
| PostgreSQL startup readiness | 1 | In Progress | Gate source/generated CI and Compose startup on final loopback TCP readiness, with bounded failure; never treat the temporary initialization socket as service readiness. | [#38](https://github.com/ppenumatsa1/agent-blueprints/issues/38) records socket-ready/TCP-unready observations on disposable PostgreSQL 16.15 and 17, an initial failed `createdb`, and a TCP-gated 72/72 source/generated retry on historical head `8b3c357`. The correction merged in [#17](https://github.com/ppenumatsa1/agent-blueprints/pull/17) as `0c1297c`; exact-head [run 45027444227](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45027444227) passed six jobs, including source and generated Compose checks. #58's historical head `9f9e16f` passed seven jobs in [run 45412773532](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45412773532); its same-tree head `787766c` passed seven in [run 45418532803](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45418532803). #59 head `88de9e4` passed seven in [run 45419227019](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45419227019). Earlier #60 head `7398ad9` passed seven in [run 45444899975](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/45444899975); later heads require their own CI. | Review current-head CI and merge this documentation reconciliation before considering #38 closure. Local/CI evidence does not establish Azure managed PostgreSQL readiness. |
| Independent blueprint instantiation | 1 | In Progress | Generate a self-contained project that builds, runs and tests without this repository; keep its synthetic readiness report distinct from trusted evidence. | [Generator](../scripts/instantiate_maf.py); `maf-independent` passed at exact #17 head `b633539` in run 44955776238. Synthetic report remains unverified (approval/recovery passed; explanation/hint unverified; unsigned validator exit 1). Independent trust/provenance tracked in [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21). | Continue independent trust administration; schema validation is not a release gate. |
| Business state, approvals, and idempotency (P1-06) | 1 | In Progress | Persist isolated business and approval state and prevent duplicate or unauthorized database actions across both specified crash windows. | [Core tests](../blueprints/maf/workflow/backend/tests/test_core.py), including both worker-kill windows; exact #17 `maf-core` and `maf-independent` jobs passed at `b633539` in run 44955776238. External effects remain outside this guarantee. | Preserve tested local guarantees; do not claim universal exactly-once behavior. |
| Consequential external side-effect authorization and idempotency (P0) | 1 | Blocked | Before consequential remote effects, require service-specific authorization, verified downstream idempotency and authoritative reconciliation; otherwise fail closed and use manual resolution rather than retrying an ambiguous effect. An outbox only persists intent; it cannot deduplicate an external effect after a lost acknowledgment. | The opt-in local pattern and separate durable synthetic downstream are exercised by `backend/tests/test_external_effect.py`; it passes a shared five-second budget, treats timeout as unknown, and reconciles before retry. Its `case:{id}:action` key covers one immutable action per case; future proposal-version/action/target identity follows merged #40. See [architecture](../blueprints/maf/workflow/docs/architecture.md). This is not evidence for a real service or a Python sandbox. Track [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32), #20 and #22. | Independently verify real adapter enforcement of deadlines, authorization, retention and reconciliation before consequential effects; keep #32 open. |
| Authenticated FastAPI service (P1-07) | 1 | In Progress | Validate Entra tokens, scopes, roles, and record access; support optional delegated OBO and explicit errors. | [API security tests](../blueprints/maf/workflow/backend/tests/test_security.py); exact #17 `maf-core` and `maf-independent` jobs passed at `b633539` / run 44955776238. Synthetic principals do not establish live Entra/OBO; track [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27). | Verify live Entra/OBO with separately authorized configuration; rerun exact-head CI for later tree/base changes. |
| Accessible React client (P1-08) | 1 | In Progress | Use MSAL and show submission, status, approval, rejection, and error states without service secrets. | Source/generated frontend tests, build and CSP passed in #17 run 44955776238 on `b633539`; live sign-in and accessibility assessment remain outstanding under [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27). | Verify interactive sign-in, accessibility, and the generated application. |
| Framework-native durable MAF workflow (P1-09) | 1 | In Progress | Use native local file checkpoints for isolated pause, resume, rejection, and recovery; keep hosted storage separate. | [Local host](../blueprints/maf/workflow/backend/app/workflows/host.py); exact #17 `maf-core` and `maf-independent` jobs passed at `b633539` / run 44955776238. Hosted MAF/checkpoints [#19](https://github.com/ppenumatsa1/agent-blueprints/issues/19), caller binding [#22](https://github.com/ppenumatsa1/agent-blueprints/issues/22), lost response [#20](https://github.com/ppenumatsa1/agent-blueprints/issues/20). | Keep hosted recovery deferred until these security-critical contracts are implemented and independently verified; deferral is not a waiver. |
| Tests, evaluations, and GitHub Actions (P1-10) | 1 | In Progress | Produce real local/CI artifacts and profile-correct readiness results, including negative cases. | Exact-tree CI [44955776238](https://github.com/ppenumatsa1/agent-blueprints/actions/runs/44955776238) passed at `b633539`; generated verifier passed 44 tests with no skips or expected failures. Producer observed approval/recovery passed, explanation/hint unverified; unsigned validator exit 1. Track evaluations/hints [#25](https://github.com/ppenumatsa1/agent-blueprints/issues/25) and trust [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21). | Add agent evaluation and browser evidence; maintain independently controlled attestations. |
| Privacy-safe observability (P1-11) | 1 | In Progress | Correlate request and workflow signals with allowlisted attributes, privacy canaries, one supported provider, native spans with raw capture off, and failure-isolated export. | The historical `3aa389f` leak/fix evidence remains in the [journal](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#pr-14---native-global-instrumentation-privacy-failure). PR #49 now has a passed version-5 start trace: one marked app-owned root, 101 hosted and 37 API spans, Foundry visibility, exact revision/version/conversation/case metadata, zero correlated exceptions/exporter failures/content capture, and zero effects while pending. The verifier classifies only the external caller and AgentServer platform contexts as expected boundaries. Resume/link proof remains blocked rather than weakened. | Require the distinct reviewer credential and one correlated start-resume pair before closing [#26](https://github.com/ppenumatsa1/agent-blueprints/issues/26). |
| Local prototype demonstration (P1-15) | 1 | Planned | Demonstrate the complete synthetic workflow and readiness report; record actual elapsed time and limitations. | [Phase 1 plan](implementation-plan.md#phase-1-maf-workflow-golden-path); 2–3 hour objective not measured. Track [#29](https://github.com/ppenumatsa1/agent-blueprints/issues/29). | Run and document a representative synthetic demo; this issue does not authorize cloud deployment. |
| Foundry Hosted Agents compatibility (P1-12) | 1 | Blocked | Record framework, protocol, identity, per-user session isolation, checkpoint, credential-lifecycle, and approval/resume compatibility evidence; local checks are not a hosted deployment. | [Hosted pattern and lost-response investigation](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---hosted-caller-binding-and-lost-responses) and [delegated session isolation clarification](../blueprints/maf/workflow/docs/design/issues-changes-fixes.md#2026-11-21---delegated-session-isolation-and-debugger-evidence). The platform does not fence delegated users sharing a session; a trusted app must authorize each principal's session, map authenticated callers to distinct sessions and reject unchecked client IDs. Platform-generated `x-agent-user-id` is a different header from the opaque app-supplied `x-ms-user-identity` scoping value derived from the validated principal; do not assume their values match. Equivalence and binding to that principal are unsupported and unverified, and the scoping value is not authorization. No bridge or mapping tests, host integration, hosted secret delivery/rotation, or host-managed checkpoint integration is implemented/live verified. Local one-shot AgentServer task IDs reran fresh after terminal completion and are not persistent deduplication; hosted semantics remain unknown. Exact wheel source exposes `response_id` in the request-aware factory before checkpoint preparation/parsing/run claim, but safe caller-bound claims, per-continuation reservations, pending-reply/action ordering, idempotent side effects, and same-response recovery remain unproven. PostgreSQL CAS is only a candidate, not a fix. The scoping value is not a credential and end-user bearer/OBO tokens must not be persisted. Lost `response.id` recovery remains unresolved. | Implement and test caller-to-session authorization before hosted use; validate any task/CAS recovery scheme, then coordinate package/API compatibility, workload networking, credential lifecycle and app lifecycle; establish unambiguous lost-response reconciliation before safely retrying ambiguous creates. |
| ACA fallback compatibility (P1-13) | 1 | Planned | Verify a separately selected container recovery strategy without assuming Foundry checkpoint ownership. | [Phase 1 plan](implementation-plan.md#phase-1-maf-workflow-golden-path) | Prepare fallback only if selected. |
| Azure deployment preparation (P1-14) | 1 | In Progress | Independently copied Bicep/azd compiles and tests without Azure credentials; default configuration avoids public unauthenticated API exposure, documents scoped roles and explicit network gaps, and requires separate approval before provisioning. | Exact #17 run 44955776238 passed `maf-infrastructure` and generated infrastructure checks on `b633539`; read-only Azure subscription/resource-group listing previously returned HTTP 200, but no resource was changed and service connectivity/write access remain unverified. Staged graph is not wired or deployed. Track IaC wiring [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18), managed DB operations [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24), and separately authorized deployment [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28). | Finish offline prerequisites and obtain explicit authorization. Live deployment should produce hosted/cloud evidence and need not wait for all live-verification issues to close. |
| Specification Studio interoperability | 6 | Blocked | Validate the versioned handoff with an actual producer or a reviewed lossless adapter. | [Handoff contract](readiness-contract.md#specification-studio-handoff); issue [#33](https://github.com/ppenumatsa1/agent-blueprints/issues/33). | Obtain a real producer artifact when available; this remains outside Phase 1 and does not authorize implementation. |
| Permanent standalone reference application (P1) | 1 | Blocked pending authorization | Deliver a synthetic, independently owned application with no source-repository runtime dependency and documented extension/operational boundaries. | Required P1 deliverable tracked in [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30); no permanent repository has been authorized or created. | Obtain separate explicit repository authorization, then verify clean clone/build/run/test and independent contracts. |
| App/API Blueprints roadmap | Later | Planned | Establish separately authorized API/web-app paths and repositories. | Roadmap [#34](https://github.com/ppenumatsa1/agent-blueprints/issues/34); [Repository boundaries](software-factory-overview.md#repository-boundaries). | Keep out of phase and obtain separate authorization before implementation. |

### Azure/Foundry Workstream A

| Acceptance criterion | Status | Evidence | Next action |
| --- | --- | --- | --- |
| Generate an independently owned native MAF Responses host without a custom orchestrator/checkpointer | Implemented; locally verified 2026-11-22 | [Hosting report](azure-foundry/hosting.md); 41 generated hosted tests, 16 publisher/generator tests, and generated Ruff check/format passed. The explicit API bridge uses only `/conversations` and `/responses`, omits caller-supplied `agent_session_id`, and prebinds authenticated human authority to the server-selected conversation before dispatch. Exact C `2a04d5be3013e782a7c1222b2a16a7047cbb15cd` passed normal API composition and all six PR checks. | Keep live hosting, managed identity, RBAC, network, and checkpoint behavior unverified until separately authorized deployment. |
| Preserve application-owned PostgreSQL business state and local filesystem checkpoint behavior | Implemented; locally verified 2026-11-22 | Eight generated workflow tests, 39 focused generated backend tests on PostgreSQL 17, and ORS-001..009 passed. Exact C `2a04d5be3013e782a7c1222b2a16a7047cbb15cd` proved one decision/action, null checkpoint fields, and no hosted PostgreSQL connectivity through the protected API. | Keep direct hosted-to-PostgreSQL removed and preserve authenticated application prebinding before hosted start/resume. |
| Reject unauthorized/cross-channel resume and avoid ambiguous POST replay | Implemented; locally verified 2026-11-22 | Generated tests cover platform-session conflict rejection, conversation/channel refusal, API-workload versus human identity separation, missing pre-established owner/reviewer binding refusal, Responses pending/malformed acknowledgments, managed-identity internal API authorization, exact schemas, stable idempotency and ambiguous-write no replay. Exact C `2a04d5be3013e782a7c1222b2a16a7047cbb15cd` adds terminal exact-intent bridge replay with zero new Responses dispatch plus conflicting-intent and unauthorized-actor refusal. | Verify deployed identities and authoritative reconciliation behavior before any live invocation. |
| Pin current public SDK/source-publish compatibility without private patches | Implemented; locally verified 2026-11-22 | [Compatibility matrix](azure-foundry/hosting.md), SDK-drift tests, deterministic source archive test, two-phase identity/readiness no-replay test, and 68-test repository contract run (2 documented adapter skips) | Recheck pins at deployment time; do not publish on failed drift tests. |

## Issue-linked open backlog

The following links attach concrete acceptance work to the matching rows
above; none marks Phase 1 or deployment complete.

| Checklist capability | Tracked work |
| --- | --- |
| P1-01–03: contract approval, evidence provenance, independent trust | [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21) |
| P0: consequential external effects require explicit authorization and idempotency | [#32](https://github.com/ppenumatsa1/agent-blueprints/issues/32) |
| P1-07–08: live Entra/OBO, interactive authentication and accessibility | [#27](https://github.com/ppenumatsa1/agent-blueprints/issues/27) |
| P1-09/P1-12: hosted MAF packaging and host-managed checkpoints | [#19](https://github.com/ppenumatsa1/agent-blueprints/issues/19); caller/session authority [#22](https://github.com/ppenumatsa1/agent-blueprints/issues/22); lost-response and side-effect recovery [#20](https://github.com/ppenumatsa1/agent-blueprints/issues/20) |
| P1-10: real agent evaluation and browser-hint evidence | [#25](https://github.com/ppenumatsa1/agent-blueprints/issues/25); independent attestation [#21](https://github.com/ppenumatsa1/agent-blueprints/issues/21) |
| P1-11: verified cloud telemetry and trace propagation | [#26](https://github.com/ppenumatsa1/agent-blueprints/issues/26) |
| Developer tooling: cross-platform and interactive debugger verification | [#23](https://github.com/ppenumatsa1/agent-blueprints/issues/23) |
| P1-13: explicitly selected ACA workflow alternative | [#31](https://github.com/ppenumatsa1/agent-blueprints/issues/31) |
| P1-14: staged IaC wiring, managed database operations, deployment | [#18](https://github.com/ppenumatsa1/agent-blueprints/issues/18), [#24](https://github.com/ppenumatsa1/agent-blueprints/issues/24), [#28](https://github.com/ppenumatsa1/agent-blueprints/issues/28) |
| P1: reusable model, agent, prompt, tool and executor extension patterns | [#35](https://github.com/ppenumatsa1/agent-blueprints/issues/35); typed contracts and generated synthetic fixture are under review on the stacked workstream branch; actual provider calls and hosted semantics remain unverified. |
| P1-15: measured local synthetic demonstration | [#29](https://github.com/ppenumatsa1/agent-blueprints/issues/29) |
| Phase 0 Specification Studio handoff | [#33](https://github.com/ppenumatsa1/agent-blueprints/issues/33); separate producer contract in [readiness-contract.md](readiness-contract.md#specification-studio-handoff) |
| P1 permanent standalone reference application | [#30](https://github.com/ppenumatsa1/agent-blueprints/issues/30); separate explicit repository authorization is required |
| Later App/API blueprint roadmap | [#34](https://github.com/ppenumatsa1/agent-blueprints/issues/34); out of phase and requires separate authorization |

## Azure/Foundry Workstream D

| Capability | Status | Acceptance criteria | Evidence | Next action |
| --- | --- | --- | --- | --- |
| Privacy-safe end-to-end correlation | Version-9 automatic and pending traces passed; resume separately blocked | Correlate API, Foundry, native MAF workflow, and deterministic business stages with request/case/trace/conversation/agent/deployment identifiers; require model/token spans only when the real path invokes a model; exclude content and secrets. | Exact source `a302e939...`, hosted `order-resolution:9`, and API revision `a302e939` passed the 16/16 signal comparison. The two traces contain 243 spans: 26 API and 217 hosted. Pooled-borrow `database.connect` is zero, physical database visibility remains, Foundry dependencies remain 128, and exporter failures, optional startup exceptions, raw content, and payload markers are zero. Internal edges resolve with only the two expected platform boundaries. | Preserve the automatic and pending proofs; obtain the distinct reviewer credential and verify resume plus the explicit durable trace link without weakening authorization. |
| Real-provider evaluation and browser E2E | Implemented locally; externally blocked live | Run real-provider evaluation only when explicitly configured, never synthesize provider success, and run actual local/live Chromium automation with revision-bound evidence. | The live runner enforces distinct delegated owner and reviewer object IDs. Only the owner/operator identity is currently available; no provider or authenticated dual-user Chromium pass is claimed. | Supply a second delegated Entra user with `workflow.read workflow.approve` and `Workflow.Approver`, consented for the API, plus an authenticated browser state. |
| Hosted failure injection and ORS | Partially passed; remaining cases blocked | Observe ORS-001–009 and all bounded synthetic failure/recovery cases without hidden retry or duplicate effects; preserve unknown outcomes until authoritative reconciliation. | Live Azure passed ORS-001, ORS-004, ORS-006, ORS-007, every ORS-008 variant, and the ORS-009 owner authorization negative (HTTP 403, pending, one denial, no effect). Successful hosted cases exposed a normalization defect because `hosted_workflow_finished` was not counted as terminal; the corrected query and hosted idempotency regression require one terminal event. ORS-002, ORS-003, ORS-005, approval/rejection, and decision/restart crash windows remain blocked by the missing distinct reviewer. | Deploy the exact fix, rerun ORS-001/004 terminal checks, then execute the reviewer-dependent matrix when the delegated prerequisite exists. |
| Immediate failed hosted Responses create | Implemented; locally verified | Preserve the returned ID and surface known failure on first call and same-key replay without another POST. | Hosted client/bridge regressions and generated [PostgreSQL restart regression](../profiles/order-resolution/overlay/backend/tests/test_order_resolution_api.py) with fake Responses transport. | Apply the profile migration before deployment. Later background failures, HTTP 429 replay safety, and authoritative reconciliation remain unverified. |
| Independent release readiness | Blocked for production | Preserve immutable implementation/Azure runtime evidence as `passed`, `failed`, `blocked`, or `unverified`; bind cloud evidence to exact source/deployment revisions; keep the release manifest diagnostic and non-authorizing. | Exact-head CI run `45275635199` passed all seven jobs. Deployment verification passed 32/32 checks for hosted version 9, API revision `a302e939`, immutable image digests, health/auth boundaries, and managed-identity PostgreSQL TLS. The bounded signal comparison passed 16/16 checks. These diagnostics do not authorize production. | Obtain distinct-reviewer HITL resume/link evidence, retain the broad PostgreSQL rule until a validated replacement API and operator path exists, and do not merge PR #49. |
