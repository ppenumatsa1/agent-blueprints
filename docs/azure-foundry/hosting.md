# Azure/Foundry Workstream A: native MAF hosting

Status date: 2026-11-22

This report covers the source and mocked/local compatibility work for the
generated Order Resolution application's Microsoft Foundry Hosted Agent. It
does not claim that an agent version was published, an Azure resource was
created, RBAC was changed, or a live hosted continuation was verified.

## Runtime and state boundary

`profiles/order-resolution/hosted-agent` is copied into every generated Order
Resolution project. Its `ResponsesHostServer` receives a request-aware
`workflow=` factory, creates a fresh native MAF workflow for each request, and
uses the SDK `CheckpointStoreProvider`. The hosted workflow does not import or
configure the generated API's `FileCheckpointStorage`.

The state boundary is deliberate:

| State | Owner |
| --- | --- |
| Hosted workflow checkpoint, pending-response authority, response/session state | Foundry hosting and native MAF checkpoint provider |
| Local development workflow checkpoint | Generated API's private `FileCheckpointStorage` |
| Case, proposal, opaque hosted request correlation, approval decision, audit, effect claim and reconciliation | Application-owned PostgreSQL |
| Ambiguous Responses/publish operation claim | Durable application/operator journal implementing the narrow interfaces below |

No custom workflow orchestrator or checkpoint provider is present. PostgreSQL
does not serialize or replace whole MAF workflows.

## Protocol and authorization contract

The host accepts protocol `responses` version `2.0.0`. A start request contains
exactly `{"case_id":"<uuid>"}`. A resume uses a
`function_call_output` for the framework-issued pending request ID and a strict
`OrderResolutionDecision` containing:

- case and proposal version;
- action and destination identity;
- framework approval handle;
- fixed `foundry-responses` channel;
- approved/rejected decision;
- conversation and hosted session bindings.

The parser first calls the public `HostedResponseRequest.get_workflow_responses()`
API so the SDK validates native pending-request authority. The application
adapter then reauthorizes the resolved principal, rejects a different caller,
session, conversation or channel, binds the native handle to the current
proposal at pause creation, and records the application-owned decision before
the workflow continues. Client/model-supplied identity is never treated as
authority.

AgentServer's `scope.user_id` is an opaque platform-resolved identity. It is not
assumed to equal an Entra object ID or the API subject. The hosted container
uses `HttpHostedBusinessStore` for both `HostedIdentityBindings` and
`HostedBusinessStore`. It calls only the authenticated internal API base in
`ORDER_RESOLUTION_API_ENDPOINT`, with a `DefaultAzureCredential` token for
`ORDER_RESOLUTION_API_SCOPE`.

The frozen generated API base is `/api/internal/hosted/v1`. The deployment
therefore sets `ORDER_RESOLUTION_API_ENDPOINT` to the API origin plus that
prefix, requests the configured API application ID URI with `/.default`, and
grants the hosted version identity only the dedicated
`Hosted.Workflow.Invoke` application role.

```python
class HostedIdentityBindings(Protocol):
    def resolve_start_principal(
        self, *, case_id: UUID, caller: CallerContext, conversation_id: str
    ) -> Principal: ...
    def authorize_resume(
        self,
        *,
        case_id: UUID,
        caller: CallerContext,
        conversation_id: str,
        channel: str,
    ) -> Principal: ...
```

The opaque Foundry caller fields and hosted managed-identity app role cannot
establish end-user authority. Before native start or resume, an authenticated
application command must pre-establish the exact case, principal, Foundry
`user_id`, session, conversation and channel binding after server-selected
conversation creation and before Responses dispatch. The hosted
`/bindings/start` and `/bindings/resume` calls are verification-only gates: they
return the already-bound owner or reviewer Principal and must return an
authorization failure when the binding is absent or mismatched. They must never
assign a case owner/reviewer from hosted correlation input. A different caller,
session, conversation, channel, or unchecked client ID fails closed.

The generated API loads the explicit factory module spec
`order_resolution_hosted.bridge:build_workflow_host`. Its narrow composition
contract is:

```python
def build_workflow_host(
    settings,
    store,
    authority_bindings,
    operation_journal,
) -> ResponsesWorkflowHost: ...
```

`ResponsesWorkflowHost.start(case_id, actor)` creates or reconciles the
server-selected conversation, persists the authenticated owner binding, then
dispatches the native Responses start. `resume(case_id, actor,
decision_command)` loads the existing conversation/session, persists the
authenticated reviewer and exact decision intent, then sends one structured
`function_call_output`. The authority adapter owns those direct PostgreSQL
bindings; Agent A does not apply or record the business decision in this API
bridge. Stable operation IDs are `case:{id}:conversation`, `case:{id}:start`,
and `case:{id}:decision:{proposal_version}`. There is no generic `/runs`
protocol or fallback host, and missing factory composition fails closed. The
bridge acquires Foundry tokens only through
`ManagedIdentityCredential(client_id=settings.api_managed_identity_client_id)`;
it does not fall back to a developer or ambient credential.

Generation copies only `bridge.py` and `client.py` into the backend build
context as a lightweight `order_resolution_hosted` package with a non-eager
initializer. The backend image copies that package directly and does not import
the sibling hosted-agent source, expand its Docker context to the repository
root, or install the hosting SDK. The full hosted package initializer is also
non-eager. Instantiation tests require byte-for-byte API/hosted client and wire
contract parity plus an import resolved from the backend directory.

The API implements the exported `HostedBusinessStore` seam against its
application-owned PostgreSQL state:

```python
class HostedBusinessStore(Protocol):
    def prepare_hosted_approval(
        self, case_id: UUID, candidate_request_id: str, *, channel: str
    ) -> Proposal: ...
    def claim_hosted_decision(self, decision: DecisionRecord) -> DecisionRecord: ...
    def finish_hosted(self, case_id: UUID) -> None: ...
```

`prepare_hosted_approval` atomically persists or returns one stable opaque
request ID for the business pending state. Agent A supplies that ID to native
`request_info(request_id=...)`. `claim_hosted_decision` authorizes and records
one decision without requiring a local checkpoint ID. `finish_hosted` marks
the business projection complete only after the native executor applies the
approved/rejected or automatic result. These methods may correlate the opaque
request ID, but must not store Foundry checkpoint bytes or fabricate a local
filesystem checkpoint ID.

The HTTP adapter uses the case-bound routes
`POST /cases/{id}/bindings/start`, `/bindings/resume`, `/read`,
`/proposal/read`, `/approvals/prepare`, `/decisions/claim`,
`/effects/apply`, and `/finish`. Each request carries flat caller, session,
conversation, channel, and principal-kind fields as applicable. The decision
route receives the original native handle and resolves the authoritative actor
API-side; the hosted process does not manufacture an actor identity. Every
state-changing call carries a stable `Idempotency-Key`; lost or malformed
acknowledgments become ambiguous and are not replayed automatically. Case
responses omit checkpoint fields; the adapter constructs only local `None`
placeholders required by the existing domain model and sends no checkpoint
bytes.

Public hosted-agent egress has no isolation or stable source-IP guarantee.
Therefore the hosted container receives no database URL, PostgreSQL
credential, TLS root, or database identity setting and never opens PostgreSQL.
The protected API endpoint remains responsible for authorization, network
access, migrations, and database pooling.
The source requirements retain pinned `psycopg[binary]==3.3.9` only because
the shared generated `app.domain.models` module imports `psycopg.Connection`
at module load. Package presence is not a hosted database path and supplies no
DSN, credential, network access, pool, or connection attempt.

## Responses client and lost acknowledgments

`order_resolution_hosted.client.ResponsesClient` uses
`DefaultAzureCredential` with `https://ai.azure.com/.default`, sends
`store=true`, binds an explicit conversation and `agent_session_id`, and emits
structured `function_call_output` resumes.

Every create has an application operation ID and canonical request digest.
`OperationJournal.claim` must atomically return `OperationClaim(acquired=True)`
only for the process that inserted the new claim. An existing `pending` record
has no current owner proof, becomes `unknown`, and is not sent again. A
concurrent original owner may still complete its one in-flight request and
record the authoritative acknowledgment. Identical acknowledged duplicates
return the recorded remote ID; conflicting duplicates fail.

A connection error, timeout, 5xx, malformed 2xx JSON, or success body without
an authoritative ID changes the operation to `unknown`; the client does not
replay that POST. Malformed response bodies are not retained in the journal or
surfaced in the error. `reconcile_acknowledgment` requires exactly one
authoritative remote ID supplied by a trusted query/operator path. An empty or
ambiguous search does not prove absence and leaves the operation `unknown`.

The included in-memory journal is only for local tests. Agents B-D must supply
a durable journal with atomic insert/claim ownership and update semantics and
an operator-visible reconciliation path before hosted use.

## Source package and publishing

Generated projects receive
`scripts/foundry/publish_order_resolution_hosted.py`. It creates a deterministic
ZIP containing `main.py`, pinned `requirements.txt`, the hosted package and the
generated `backend/app` source. The source contract uses:

- runtime `python_3_13`;
- entry point `python main.py`;
- remote dependency resolution;
- Responses protocol `2.0.0`;
- the explicit runtime allowlist documented below.

The model deployment name is required configuration and is not hard-coded.
The reported East US 2 catalog examples (`gpt-4.1-mini` `2025-04-14` and
`gpt-4o-mini` `2024-07-18`) are deployment choices for the authorized
deployment workstream, not runtime defaults.

The publisher fallback calls the public
`AIProjectClient.agents.create_version_from_code` API with a
`HostedAgentDefinition`, ZIP SHA-256, operation metadata, and `retry_total=0`.
An exception or missing returned version is `unknown` and cannot be replayed
until `list_versions` finds exactly one version with matching operation ID,
publication digest, and archive digest.

The publication digest binds the project endpoint, explicit project resource
ID, target agent name, source archive digest, CPU/memory, Python runtime, entry
point, dependency resolution, protocol/version list, model deployment, and
host environment inputs. Reusing an operation journal for any different target
or configuration fails closed before an SDK create. Publishing requires
`FOUNDRY_PROJECT_ID` plus an explicit hosted runtime allowlist:

- `FOUNDRY_PROJECT_ENDPOINT`;
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`;
- `ORDER_RESOLUTION_API_ENDPOINT`;
- `ORDER_RESOLUTION_API_SCOPE`;
- `ORDER_RESOLUTION_API_TIMEOUT_SECONDS`.

The project endpoint in the runtime environment must match the publication
target. Every allowlisted value is injected into the public
`HostedAgentDefinition` and bound into the publication digest. Embedded
database settings, non-HTTPS API endpoints, invalid API scopes, undeclared
runtime variables, and invalid timeout values fail before create.

The file journal uses an OS-level lock and a unique owner token. Only the
process that atomically creates a new `pending` claim may call the SDK. A
preexisting pending record becomes `unknown` and is not resent; a concurrent
original owner may still record its one authoritative result. The helper
packages or publishes only; it does not provision infrastructure or change
RBAC.

After an acknowledged create, the CLI safely polls the public
`agents.get_version(agent_name, agent_version)` GET until the platform-created
identity is available. The first phase returns the identity even when the
version is still creating, so the infrastructure workstream can grant
the hosted identity access to the protected API before any invocation.
Rerunning the identical operation with `--require-active` performs no create and
polls the same version until it is active. The JSON record includes the agent
version, data-plane version ID, agent GUID, provisioning status, identity
principal (object) ID, and identity client ID as `agent_version`,
`agent_version_id`, `agent_guid`, `provisioning_status`,
`identity_principal_id`, and `identity_client_id`. A polling timeout leaves the
create acknowledged in the journal; rerunning the same operation may safely
retry discovery/readiness. The SDK does not expose a documented ARM resource
ID for the hosted version, so callers must not invent one.

## Compatibility matrix

| Capability | Result | Evidence / limitation |
| --- | --- | --- |
| Native MAF request-aware workflow hosting | Verified locally | `ResponsesHostServer(workflow=..., parse_response=...)` signature and mocked protocol tests |
| Standard hosted checkpoint provider | Verified locally | Public `CheckpointStoreProvider(allowed_checkpoint_types=...)`; no custom provider or local file storage in hosted composition |
| Responses protocol `2.0.0` manifest | Verified locally | Deterministic publisher contract and SDK model construction test |
| Structured native approval resume | Verified locally | Generated package tests validate stable hosted request identity, decision recording, business completion without a local checkpoint ID, and exact caller/session/conversation/channel binding |
| Authenticated API-to-Responses bridge | Interface and ordering verified locally; C composition pending | Explicit factory creates/reconciles the conversation, prebinds authenticated owner/reviewer authority before dispatch, and uses only `/conversations` plus `/responses`; no generic `/runs` fallback |
| Application-owned hosted business seam | Functional composition verified; authorization integration blocked | Agent A's adapter and Workstream C `60fd83fc05acc290aab3ed96f8f8c255e493d28d` passed the real-PostgreSQL lifecycle, but that C revision created owner/reviewer bindings from opaque hosted input and is rejected as authorization evidence |
| Protected API business port | Wire/idempotency verified; binding correction required | Exact C revision `60fd83fc05acc290aab3ed96f8f8c255e493d28d` passed bind/read/prepare/decision/effect/finish over loopback HTTP, but integration must be rerun against verification-only binding endpoints backed by an authenticated application command |
| Managed-identity token acquisition | Verified locally | Mock credentials verify `https://ai.azure.com/.default`, the dedicated internal API `api://.../.default` scope, and Authorization headers |
| Source-code publishing API | Verified locally | Public signature/model test and no-retry mocked publish test |
| Hosted version identity query | SDK surface verified; live identity unverified | Public `get_version` returns `AgentVersionDetails.instance_identity.principal_id/client_id`, `id`, `agent_guid`, and provisioning status |
| Exact dependency compatibility | Verified locally | Pinned environment imports and SDK-drift assertions |
| Hosted per-user/session checkpoint isolation | Documented, not live verified | Platform behavior is relied on only after application mapping; no Azure deployment was performed |
| Live MI/RBAC access and secret delivery | Unverified | Requires authorized deployed identities and least-privilege role validation |
| Live pause, restart and cross-instance resume | Unverified | Requires a deployed hosted agent and controlled recovery test |
| Lost Responses/conversation create negative proof | Unsupported/unverified | No documented idempotency key or bounded negative read-after-write guarantee; remain `unknown` |
| Restart/concurrent pending client claim | Verified locally | Existing pending claims are not resent; only the atomic original claimant may complete the one in-flight POST |
| Malformed successful create acknowledgment | Verified locally | Malformed 2xx JSON becomes `unknown` without response-body evidence and cannot be replayed |
| Publication target/configuration identity | Verified locally | Digest covers project endpoint/ID, agent, archive, runtime, entry point, protocol, model and hosted configuration; conflicting reuse fails |
| Model response quality and catalog availability | Unverified | Model name is injected; no model was deployed or invoked |
| Telemetry export and hosted trace correlation | Unverified | Requires deployed Application Insights integration |

## Local validation evidence

- 38 generated hosted-runtime tests passed, including absent and mismatched
  pre-established owner/reviewer binding refusal and API bridge
  conversation/prebind/dispatch ordering.
- 16 publisher/generator tests passed, including restart/concurrent publish
  exclusion and complete publication identity conflicts.
- Generated Ruff check and format check passed across 93 Python files.
- 39 focused generated backend tests passed on PostgreSQL 17.
- ORS-001 through ORS-009 passed without skips on PostgreSQL 17.
- The repository contract suite passed 68 tests with the two documented
  adapter-selection skips.
- Exact Workstream C revision
  `60fd83fc05acc290aab3ed96f8f8c255e493d28d` passed the composed PostgreSQL 17
  protected-API and native `/conversations` plus `/responses` wire proof in
  6.273 seconds. The proof used A's exact `OperationClaim(record, acquired)`
  types, repeated acknowledged creates with zero replay, one decision/action,
  and null business checkpoint fields. This is functional wire/idempotency
  evidence only: security review rejected that C revision because its bind
  endpoints manufactured owner/reviewer authority from opaque hosted caller
  input. Final A/C compatibility requires a new C revision that only verifies
  bindings pre-established by an authenticated application command, plus a
  repeated composed proof with absent/mismatched binding negatives.
- Two independently built source archives matched SHA-256
  `3ccb46568c228d4112ad6c2e4c6d482dab37be2804f657877ddf567a51b4b3d7`
  and contained 56 files.
- A generated backend image built from its normal backend-only context using
  the configured Python package proxy. An in-container import resolved
  `order_resolution_hosted.bridge` and `order_resolution_hosted.client` from
  `/app/order_resolution_hosted`, verifying that the API-side package is
  present without a sibling source path or hosted SDK dependency.
- Normal API startup with C's concrete backend-native `WorkflowHost`
  composition remains unverified until C supplies the corrected immutable
  composition revision.

## Pinned SDKs

The hosted source pins:

- `agent-framework-core==1.26.0`
- `agent-framework-foundry==1.16.2`
- `agent-framework-foundry-hosting==1.0.0b261112`
- `azure-ai-agentserver-core==2.3.1b1`
- `azure-ai-agentserver-responses==2.4.0`
- `azure-ai-projects==2.11.0`
- `azure-identity==1.27.0`

The hosted package is prerelease and installation requires prerelease
resolution. Tests fail on missing versions or public method drift rather than
using private SDK patches. In particular, the reference implementation's
private `_platform_headers` mutation is rejected.

## Official sources

- [Host a Microsoft Agent Framework workflow in Foundry](https://learn.microsoft.com/en-us/agent-framework/hosting/foundry-hosted-agent)
- [Deploy a hosted agent from source code](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/deploy-hosted-agent-code?view=foundry)
- [Foundry hosted agents concepts](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/hosted-agents?view=foundry)
- [Foundry agent runtime components](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/concepts/runtime-components?view=foundry)
- [Azure AI Projects Python API reference](https://learn.microsoft.com/en-us/python/api/azure-ai-projects/azure.ai.projects.aiprojectclient?view=azure-python)
- [Azure Identity `DefaultAzureCredential`](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.defaultazurecredential?view=azure-python)
- [Foundry agent networking options](https://learn.microsoft.com/azure/foundry/agents/concepts/networking-options)

The requested `ppenumatsa1/maf-monorepo` reference commit
`45430753c5f3e75716ea3822d2b52fbb4f1c34` was unavailable. The inspected local
main and this repository's prior link use
`45430753c5f3e75716ea3822d2b2b52fbb4f1c34`; this report treats the requested
SHA as a transposition and reuses only public composition/wire patterns.
