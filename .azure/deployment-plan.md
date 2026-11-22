# Azure/Foundry Deployment Plan

## Status

Ready for Validation

## Scope and guardrails

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
| Hosted runtime | Generated source published through Agent A's public SDK fallback | No hosted-agent ACR/container mode; ambiguous creates are never replayed |
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
- API receives Foundry Agent Consumer only at the explicit hosted-agent scope
  after one acknowledged immutable version exists. It receives Monitoring
  Metrics Publisher at Application Insights scope.
- API and frontend receive AcrPull at registry scope.
- API receives Key Vault Secrets User at vault scope.
- The Foundry project identity receives Cognitive Services OpenAI User at
  account scope.
- PostgreSQL database-role creation is a separate, explicit configuration step;
  Azure RBAC does not create database principals.
- Hosted-agent principal assignments are applied only after an immutable hosted
  version exposes its principal ID.

## Operations

Scripts under `scripts/azure/` provide:

1. read-only identity, provider, region, model quota/capacity, Container Apps,
   and PostgreSQL preflight;
2. local Bicep build/lint and infrastructure contract checks;
3. independent Order Resolution generation plus guarded Azure CLI what-if and
   deployment orchestration;
4. PostgreSQL firewall and managed-identity database-principal configuration;
5. schema migration;
6. exact revision and health verification;
7. scoped Container Apps rollback; and
8. destructive teardown requiring explicit confirmation.

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
- PostgreSQL Burstable `Standard_B1ms`, 32 GiB storage, 7-day backup, no HA or
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
- [x] Bicep build/lint and eleven non-deploying contract tests pass.
- [x] Root unit suite passes: 68 tests with two expected adapter-selection
  skips.
- [x] PowerShell and Python syntax validation passes.
- [x] Status changed to `Ready for Validation`.

## Section 7: Validation proof

| Command or check | Result |
| --- | --- |
| `pwsh ./scripts/azure/validate.ps1` | Bicep build/lint succeeded; 11 infrastructure contracts passed |
| Isolated `python -m unittest discover -s tests -v` with `requirements-dev.txt` | 68 passed; 2 expected adapter-selection skips |
| PowerShell parser over `scripts/azure/*.ps1` | Passed |
| `python -m compileall -q ./scripts/azure ./infra/tests` | Passed |
| `git diff --check` | Passed |
| Azure CLI identity preflight with mismatched azd | Passed Azure CLI context and reported the unrelated azd mismatch |
| Azure CLI negative identity contracts | Wrong subscription fails before azd inspection; explicit azd mode blocks mismatch |
| Generated hosted-composition deployment gate | Current unintegrated source generation stopped before preflight/mutation on missing `hosted-agent/main.py` and cleaned temporary artifacts |
| Subscription what-if | Not run: deployment-specific Entra/admin/hosted endpoint and agent-scope values are intentionally unset |

The Azure validation workflow is intentionally incomplete and the plan remains
`Ready for Validation`, not `Validated`. Deployment-specific inputs, provider
what-if, live generated-source publication, and application verification remain
unexecuted.

## Deployment gate

The current Azure CLI identity matches the authorized context. Azure CLI mode
uses that verified context for preflight, what-if, Bicep deployment, outputs,
generated image deployment, and scoped operations; it never calls
`az account set`. The current azd identity is a different tenant/account, is
reported in evidence, and blocks only explicitly selected azd mode.

Deployment also fails before mutation unless it can instantiate an independent
Order Resolution project and find the generated backend, frontend,
`hosted-agent`, and Agent A publisher. The hosted adapter endpoint, documented
agent RBAC scope, hosted database role, stable publish operation, durable journal, PostgreSQL
administrator, and output path are mandatory explicit inputs.

The publisher contract requires `agent_version`, `agent_version_id`,
`agent_guid`, `identity_principal_id`, `identity_client_id`, and an `active`
`provisioning_status`; the data-plane version ID is not represented as an ARM
resource ID.

The generated application interface was reviewed against Agent C draft PR #48
head `b4c7ed825833c20fa6549aa5a8e206cfbe85a77d` (implementation
`395dbeb`). Agent A froze the publisher field contract above while its final
post-composition revision remains pending; live A/C composition is therefore
still unverified and deployment remains outside this plan.

## Directory application contract

`scripts/azure/configure-entra.ps1` provides non-interactive read-only
validation and an explicit `-Apply` mode for two uniquely named single-tenant
registrations. It exposes the three delegated workflow scopes, defines
`Workflow.User` and `Workflow.Approver`, configures localhost and exact
deployed SPA origins, and preauthorizes only the SPA client. Azure CLI mode
returns tenant/client/app-ID-URI values directly to the deployment orchestrator;
optional azd mode may persist the same nonsecret identifiers. It creates no
credentials or users.

Directory permissions are independent of subscription `Owner`. The operator
must be allowed to create and own app registrations or hold a reviewed
directory role. Entra deletion is a separately confirmed
`teardown-entra.ps1` operation and is not part of resource-group teardown.
