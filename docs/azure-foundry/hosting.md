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
| Hosted workflow checkpoint, pending request, response/session state | Foundry hosting and native MAF checkpoint provider |
| Local development workflow checkpoint | Generated API's private `FileCheckpointStorage` |
| Case, proposal, approval decision, audit, effect claim and reconciliation | Application-owned PostgreSQL |
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
proposal, and records the application-owned decision before the workflow
continues. Client/model-supplied identity is never treated as authority.

AgentServer's `scope.user_id` is an opaque platform-resolved identity. It is not
assumed to equal an Entra object ID or the API subject. Agents B-D must provide
`ORDER_RESOLUTION_HOSTED_IDENTITY_BINDINGS=module:function`, returning an
implementation of `HostedIdentityBindings`:

```python
class HostedIdentityBindings(Protocol):
    def resolve_principal(self, caller: CallerContext) -> Principal: ...
    def bind_start(
        self, *, case_id: UUID, caller: CallerContext, conversation_id: str
    ) -> None: ...
    def authorize_resume(
        self,
        *,
        case_id: UUID,
        caller: CallerContext,
        conversation_id: str,
        channel: str,
    ) -> None: ...
```

That adapter must persist and check the authoritative mapping from Foundry
`user_id`, `session_id` and conversation to the authenticated application
principal and case. A different channel or unchecked client session ID must
fail closed.

## Responses client and lost acknowledgments

`order_resolution_hosted.client.ResponsesClient` uses
`DefaultAzureCredential` with `https://ai.azure.com/.default`, sends
`store=true`, binds an explicit conversation and `agent_session_id`, and emits
structured `function_call_output` resumes.

Every create has an application operation ID and canonical request digest.
Identical acknowledged duplicates return the recorded remote ID. Conflicting
duplicates fail. A connection error, timeout, 5xx, or success body without an
authoritative ID changes the operation to `unknown`; the client does not replay
that POST. `reconcile_acknowledgment` requires exactly one authoritative remote
ID supplied by a trusted query/operator path. An empty or ambiguous search does
not prove absence and leaves the operation `unknown`.

The included in-memory journal is only for local tests. Agents B-D must supply
a durable journal with atomic claim/update semantics and an operator-visible
reconciliation path before hosted use.

## Source package and publishing

Generated projects receive
`scripts/foundry/publish_order_resolution_hosted.py`. It creates a deterministic
ZIP containing `main.py`, pinned `requirements.txt`, the hosted package and the
generated `backend/app` source. The source contract uses:

- runtime `python_3_13`;
- entry point `python main.py`;
- remote dependency resolution;
- Responses protocol `2.0.0`;
- injected `AZURE_AI_MODEL_DEPLOYMENT_NAME`.

The model deployment name is required configuration and is not hard-coded.
The reported East US 2 catalog examples (`gpt-4.1-mini` `2025-04-14` and
`gpt-4o-mini` `2024-07-18`) are deployment choices for the authorized
deployment workstream, not runtime defaults.

The publisher fallback calls the public
`AIProjectClient.agents.create_version_from_code` API with a
`HostedAgentDefinition`, ZIP SHA-256, operation metadata, and `retry_total=0`.
An exception or missing returned version is `unknown` and cannot be replayed
until `list_versions` finds exactly one version with both matching operation ID
and archive digest. The helper packages or publishes only; it does not
provision infrastructure or change RBAC.

## Compatibility matrix

| Capability | Result | Evidence / limitation |
| --- | --- | --- |
| Native MAF request-aware workflow hosting | Verified locally | `ResponsesHostServer(workflow=..., parse_response=...)` signature and mocked protocol tests |
| Standard hosted checkpoint provider | Verified locally | Public `CheckpointStoreProvider(allowed_checkpoint_types=...)`; no custom provider or local file storage in hosted composition |
| Responses protocol `2.0.0` manifest | Verified locally | Deterministic publisher contract and SDK model construction test |
| Structured native approval resume | Verified locally | Generated package test validates decision recording and exact caller/session/conversation/channel binding |
| Managed-identity token acquisition | Verified locally | Mock credential verifies `https://ai.azure.com/.default` and Authorization header |
| Source-code publishing API | Verified locally | Public signature/model test and no-retry mocked publish test |
| Exact dependency compatibility | Verified locally | Pinned environment imports and SDK-drift assertions |
| Hosted per-user/session checkpoint isolation | Documented, not live verified | Platform behavior is relied on only after application mapping; no Azure deployment was performed |
| Live MI/RBAC access and secret delivery | Unverified | Requires authorized deployed identities and least-privilege role validation |
| Live pause, restart and cross-instance resume | Unverified | Requires a deployed hosted agent and controlled recovery test |
| Lost Responses/conversation create negative proof | Unsupported/unverified | No documented idempotency key or bounded negative read-after-write guarantee; remain `unknown` |
| Model response quality and catalog availability | Unverified | Model name is injected; no model was deployed or invoked |
| Telemetry export and hosted trace correlation | Unverified | Requires deployed Application Insights integration |

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

The requested `ppenumatsa1/maf-monorepo` reference commit
`45430753c5f3e75716ea3822d2b52fbb4f1c34` was unavailable. The inspected local
main and this repository's prior link use
`45430753c5f3e75716ea3822d2b2b52fbb4f1c34`; this report treats the requested
SHA as a transposition and reuses only public composition/wire patterns.
