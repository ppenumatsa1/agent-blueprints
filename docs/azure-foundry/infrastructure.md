# Azure/Foundry infrastructure

## Status and scope

Azure/Foundry Workstream B prepares the public-network deployment surface for
the Order Resolution application. The implementation is ready for independent
validation; it has not provisioned, deployed, changed RBAC, configured a
database, or deleted Azure resources.

The work started from exact repository revision
`886b628fdea02f9089c385b4ed0fc46d90f375e8`. Tenant, subscription, and user
identifiers remain execution-time inputs because this is a public repository.
The authoritative implementation plan is
[`.azure/deployment-plan.md`](../../.azure/deployment-plan.md).

Public networking is an explicit milestone decision. The topology contains no
virtual network, private endpoint, private DNS zone, or private runner.
Protected public endpoints still require TLS, authentication, and
authorization. A later private-network milestone must be separately designed,
costed, and approved.

## Read-only discovery evidence

Discovery was captured on 2026-11-22 without calling `az account set` or
mutating Azure:

- Azure CLI matched the authorized user, tenant, and subscription.
- Subscription-scope effective roles included `Owner` and `Foundry User`.
- Every required provider was `Registered`: `Microsoft.App`,
  `Microsoft.Authorization`, `Microsoft.CognitiveServices`,
  `Microsoft.ContainerRegistry`, `Microsoft.DBforPostgreSQL`,
  `Microsoft.Insights`, `Microsoft.KeyVault`,
  `Microsoft.ManagedIdentity`, `Microsoft.OperationalInsights`, and
  `Microsoft.Resources`.
- Azure Developer CLI was authenticated as a different account in a different
  tenant. This is a hard deployment gate. `preflight.py` compares the Azure CLI
  account and tenant with both the azd status account and azd token claims.
- All preferred regions advertised AI Services accounts, Container Apps
  environments/apps, PostgreSQL Flexible Server, Log Analytics, and
  Application Insights.

The identity and subscription checks intentionally derive their target from
environment variables:

```powershell
az account show --only-show-errors --output json
az ad signed-in-user show --only-show-errors --output json
az role assignment list `
  --assignee <signed-in-object-id> `
  --include-groups --include-inherited `
  --scope "/subscriptions/$env:AZURE_SUBSCRIPTION_ID" `
  --output json
az provider show `
  --namespace <provider-namespace> `
  --subscription $env:AZURE_SUBSCRIPTION_ID `
  --output json
azd auth login --check-status
azd auth token --no-prompt
```

The selected-model and dependency checks used:

```powershell
az cognitiveservices model list `
  --location eastus2 `
  --subscription $env:AZURE_SUBSCRIPTION_ID `
  --output json
az cognitiveservices usage list `
  --location eastus2 `
  --subscription $env:AZURE_SUBSCRIPTION_ID `
  --output json
az rest --method get --url `
  "https://management.azure.com/subscriptions/$env:AZURE_SUBSCRIPTION_ID/providers/Microsoft.CognitiveServices/locations/eastus2/modelCapacities?api-version=2024-10-01&modelFormat=OpenAI&modelName=gpt-4.1-mini&modelVersion=2025-04-14"
az rest --method get --url `
  "https://management.azure.com/subscriptions/$env:AZURE_SUBSCRIPTION_ID/providers/Microsoft.App/locations/eastus2/usages?api-version=2024-03-01"
az postgres flexible-server list-skus `
  --location eastus2 `
  --subscription $env:AZURE_SUBSCRIPTION_ID `
  --output json
```

Current Microsoft documentation lists East US 2 for Foundry projects,
Responses API, and Agent Service:

- [Foundry Agent Service quotas, limits, regions, and models](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/limits-quotas-regions)
- [Foundry feature availability across regions](https://learn.microsoft.com/en-us/azure/foundry/reference/region-support)

Documentation support is not treated as deployment capacity. The preflight
also checks subscription model quota, the model-capacity endpoint, the
Container Apps managed-environment quota, and PostgreSQL SKU availability.

## Region and model decision

No split-region topology is selected.

| Priority | Region | Read-only result | Decision |
| --- | --- | --- | --- |
| 1 | East US 2 | Foundry project, Responses API, Agent Service, required dependent resource types, `gpt-4.1-mini` `2025-04-14`, `GlobalStandard`, 11,000 subscription quota available, 11,000 platform capacity, 42 Container Apps environments available, and `Standard_B1ms` available | Selected |
| 2 | East US | Required dependent resource types present; Global Standard `gpt-4.1-mini` quota reported 11,000 and Container Apps environments 50. The exact model-version capacity and PostgreSQL SKU result must be re-run if this fallback is considered. | Reviewed fallback, not selected |
| 3 | Central US | Required dependent resource types present; Global Standard `gpt-4.1-mini` quota reported 11,000, Container Apps environments 50, and `Standard_B1ms` was returned. Exact model-version capacity must be re-run if this fallback is considered. | Reviewed fallback, not selected |

The planned deployment is explicit rather than inferred:

| Field | Value |
| --- | --- |
| Model | `gpt-4.1-mini` |
| Version | `2025-04-14` |
| Format | `OpenAI` |
| SKU | `GlobalStandard` |
| Capacity | `10` |

Standard `gpt-4.1-mini` was rejected because East US 2 subscription quota was
fully allocated. Global Standard has sufficient subscription and platform
capacity for the requested value. `gpt-4o-mini` was available but was not
selected because the authorized design chose the compatible
`gpt-4.1-mini` deployment. No chat/embedding SKU substitution is present.

The current catalog marks `2025-04-14` as the default deployable version with
`agentsV2=true` and `responses=true`, but its lifecycle status is `Legacy` and
its listed inference deprecation date is 2027-04-14. This does not invalidate
the authorized selection today, but it is a production-lifecycle risk.
Deployment validation must recheck the catalog, and the owning team must plan
and test a supported replacement before that date.

If East US 2 fails a deployment-time capacity or availability check, the
deployment must stop. Operators must repeat the complete checks for East US
and then Central US before changing the region; scripts do not silently place
individual resources in another region.

## Resource inventory

| Resource | Purpose | Important controls |
| --- | --- | --- |
| Resource group | Workload ownership and teardown boundary | Deterministic name; `azd-env-name`, workload, owner, and environment tags |
| Foundry AI Services account | Project and model parent | System identity; local auth disabled; public authenticated endpoint |
| Foundry project | Hosted-agent control plane | System identity; Application Insights connection; optional non-shared runtime secret connection |
| Model deployment | Agent inference | Explicit model/version/SKU/capacity; no automatic version upgrade |
| User-assigned identities | API and frontend workload identities | Separate principals; no shared application secret |
| Entra API/SPA registrations | User authentication and delegated authorization | Single tenant; deterministic unique display names; no client secret or test user |
| Log Analytics workspace | Container and application logs | 30-day retention; 1 GB/day cap |
| Application Insights | Traces and metrics | Workspace based; local auth disabled |
| Container registry | API/frontend image storage | Basic SKU; admin and anonymous access disabled; identity-based pull |
| Container Apps environment | Public application hosting | Consumption profile; public network; Log Analytics integration |
| API Container App | Protected application API | TLS-only external ingress; Entra platform auth; one active revision; 0-2 replicas |
| Frontend Container App | Public web UI | TLS-only external ingress; one active revision; 0-2 replicas |
| PostgreSQL Flexible Server | Business state | PostgreSQL 17; Entra-only; TLS 1.2+; public access with exact-IP firewall rules |
| Key Vault | Optional application secrets | RBAC; soft delete; purge protection; no secret values in outputs |

Azure Verified Modules are used for stable managed identities, Log Analytics,
Application Insights, and Container Registry resources. Foundry
projects/connections, Container Apps auth, Key Vault, and PostgreSQL use
direct resource definitions where the required contract is more precise or a
suitable stable AVM was not verified.

Hosted Agent code deployment remains the responsibility of the runtime
workstream. This infrastructure does not create an ACR dependency for the
hosted agent. ACR is retained only because azd remote builds and Container
Apps require image storage for the API and frontend.

## Identity and least-privilege role matrix

| Principal | Scope | Role or database privilege | Reason |
| --- | --- | --- | --- |
| Foundry project system identity | Foundry account | Cognitive Services OpenAI User | Invoke the selected model deployment |
| API user-assigned identity | Foundry project initially | Foundry Agent Consumer | Initial fallback until Agent A can replace it with the same role at immutable agent scope |
| API user-assigned identity | Application Insights | Monitoring Metrics Publisher | Send Entra-authenticated telemetry |
| API user-assigned identity | Key Vault | Key Vault Secrets User | Resolve only configured secret references |
| API user-assigned identity | ACR | AcrPull | Pull the API image |
| Frontend user-assigned identity | ACR | AcrPull | Pull the frontend image |
| API PostgreSQL principal | Application database | Connect, schema usage, table DML, and sequence use | Runtime business persistence without schema ownership |
| Reviewed PostgreSQL administrator | PostgreSQL server | Entra administrator | Create the runtime principal and execute reviewed migrations |
| Hosted-agent version principal | Only scopes required by its runtime | Deferred until Agent A supplies an immutable version principal ID | Avoid assigning rights to an unknown or mutable principal |
| End users | No Azure workload scope | Delegated API scopes plus `Workflow.User`/`Workflow.Approver` application roles | API validates tenant, audience, scopes/roles, and record-level authorization |
| Deployment principal | New resource group/resources | Contributor plus Role Based Access Control Administrator or User Access Administrator; Owner is accepted for the authorized test subscription | Create resources and reviewed role assignments without runtime data-plane use |

The PostgreSQL role is created separately because Azure RBAC does not create
database principals. Migration ownership and runtime DML remain distinct.
The API project-scoped Foundry assignment is temporary bootstrap scope. Agent A
owns replacing it with agent scope and removing the project assignment once
the immutable hosted agent resource ID exists.

## Configuration and secret handling

- Subscription, tenant, user, API registration, and PostgreSQL administrator
  values are azd environment inputs, not committed defaults.
- `configure-entra.ps1` creates or reuses the uniquely named single-tenant API
  and SPA registrations, exposes `workflow.read`, `workflow.write`, and
  `workflow.approve`, and defines `Workflow.User` and `Workflow.Approver`.
  It outputs identifiers only, never credentials.
- PostgreSQL password authentication is disabled. Deployment tooling obtains a
  short-lived Entra token and restores affected process environment variables.
- The API receives the Foundry project endpoint, model deployment name,
  identity client ID, PostgreSQL host, and database name as non-secret
  settings.
- Optional secrets are Key Vault references resolved with the API managed
  identity. No `listKeys`, passwords, or connection strings are exported from
  the root template.
- The optional Foundry runtime database connection is off by default and must
  be populated with a reviewed secure value. It is not shared to all project
  consumers.
- Container Apps auth rejects unauthenticated API traffic with `401`; only
  `/healthz` is excluded. HTTPS is required and the token store is disabled.

## Operations and safety

| Command | Behavior |
| --- | --- |
| `pwsh ./scripts/azure/validate.ps1` | Builds and lints Bicep, then runs non-deploying infrastructure contract tests |
| `pwsh ./scripts/azure/preflight.ps1 -FromAzdEnvironment` | Performs identity, provider, permission, exact deployment region, model, quota, Container Apps, and PostgreSQL checks; fails on az/azd account or tenant mismatch |
| `pwsh ./scripts/azure/configure-entra.ps1` | Read-only validation of the deterministic API/SPA registration contract |
| `pwsh ./scripts/azure/configure-entra.ps1 -Apply` | Idempotently creates/reuses the two single-tenant registrations and records identifiers; no secret/user creation |
| `pwsh ./scripts/azure/what-if.ps1 -Location eastus2 -ParameterFile <file>` | Runs subscription-scope what-if with `ProviderNoRbac`; it does not apply the plan |
| `pwsh ./scripts/azure/deploy.ps1 -Apply -OperatorIp <current-public-ipv4>` | Explicitly provisions, temporarily allowlists the operator, configures PostgreSQL, migrates, deploys API/frontend, removes the temporary operator rule, and verifies health |
| `pwsh ./scripts/azure/configure-postgres.ps1 -Apply -OperatorIp <current-public-ipv4>` | Reconciles exact API Container App outbound IPv4 rules, temporarily allowlists the operator in a self-cleaning scope, and creates the API Entra principal |
| `pwsh ./scripts/azure/migrate.ps1 -Apply -OperatorIp <current-public-ipv4>` | Temporarily allowlists the operator, runs application-owned migrations as the Entra administrator, applies runtime grants, then removes the rule |
| `python ./scripts/azure/health-check.py` | Verifies one healthy latest Container Apps revision, public health/auth boundaries, Foundry project state, and model deployment state |
| `pwsh ./scripts/azure/rollback.ps1 -Apply -ApiRevision <revision> -WebRevision <revision>` | Restores reviewed immutable image digests from named revisions and reruns health checks |
| `pwsh ./scripts/azure/teardown.ps1 -Apply -ConfirmEnvironmentName <name>` | Destructive; verifies exact environment confirmation and the resource-group ownership tag before `azd down --purge` |
| `pwsh ./scripts/azure/teardown-entra.ps1 -Apply ...` | Separately destructive; verifies exact display names and azd-bound client IDs before deleting only the two registrations |

Deployment, configuration, migration, rollback, and teardown all invoke the
same identity preflight. Teardown never runs automatically.

## Indicative cost drivers

Retail values were queried from the Azure Retail Prices API in USD for East
US 2. They are planning inputs, not a quote; agreement, grants, region,
runtime duration, token mix, traffic, and future prices can change them.

| Driver | Indicative public retail value |
| --- | --- |
| PostgreSQL `B1MS` compute | `$0.017/hour`, about `$12.41/month` at 730 hours |
| PostgreSQL 32 GiB storage | `$0.115/GiB-month`, about `$3.68/month` |
| PostgreSQL backup above included allowance | `$0.095/GB-month` |
| ACR Basic | `$0.1666/day`, about `$5.00` per 30 days |
| Container Apps active CPU | `$0.000024/vCPU-second` |
| Container Apps active memory | `$0.000003/GiB-second` |
| Two 0.5-vCPU/1-GiB apps active 100 hours each | About `$10.80` before grants, requests, and egress |
| Log Analytics paid ingestion | `$2.76/GB`; a zero-price meter also appears, so grant applicability must be verified |
| `gpt-4.1-mini` Global Standard input | `$0.0004/1K` tokens (`$0.40/1M`) |
| `gpt-4.1-mini` Global Standard cached input | `$0.0001/1K` tokens (`$0.10/1M`) |
| `gpt-4.1-mini` Global Standard output | `$0.0016/1K` tokens (`$1.60/1M`) |
| Hosted Agent compute | Indicatively `$0.0994/vCPU-hour` plus `$0.0118/GiB-hour`; 1 vCPU and 2 GiB is about `$0.123/hour` |

Prompt/workflow-native agents have no separate agent runtime charge beyond
models and tools. Hosted Agents use dedicated container compute and can accrue
compute cost while allocated, including idle time until suspension. See the
[official Foundry Agent Service pricing page](https://azure.microsoft.com/en-us/pricing/details/foundry-agent-service/).

Dominant cost uncertainty is model token volume, Hosted Agent allocation time,
telemetry ingestion, and Container Apps active time. The template bounds
replicas, log retention/daily quota, database size/backup, and ACR tier, but it
does not manufacture a fixed workload estimate.

## Deployment prerequisites

Before any live operation:

1. Reauthenticate azd as the same authorized Azure CLI account and tenant.
2. Select an azd environment and provide all values referenced by
   `infra/main.parameters.json`, including an existing API Entra application
   contract and a reviewed PostgreSQL Entra administrator. The Entra setup
   script can create/reuse the authorized deterministic app registrations.
3. Rerun the complete preflight. East US 2 remains selected only if every
   model/dependency check passes at deployment time, including `agentsV2`,
   Responses API, lifecycle, version, quota, and platform capacity.
4. Review the subscription-scope what-if, including resource names, tags,
   roles, model capacity, public ingress, firewall inputs, and estimated cost.
5. Ensure `psql`, `uv`, Azure CLI, azd, Bicep, Docker/remote build support, and
   application migration dependencies are available.
6. Agent A must add the `azure.ai.agent` service only after the hosted source
   folder, entry point, immutable version behavior, and post-deploy principal
   are known.
7. Agent C must implement renewable managed-identity PostgreSQL token
   acquisition, replace the current Compose-only frontend proxy target, and
   confirm API/frontend environment-variable and Entra audience/issuer
   behavior. The current base cannot set
   `AZURE_APPLICATION_RUNTIME_READY=true`.
8. Agent D must define the exact hosted revision, trace, evaluation, and
   browser evidence to retain after deployment.

## Integration outputs

The root Bicep template publishes typed azd outputs rather than a shared
runtime dependency:

| Consumer | Outputs |
| --- | --- |
| Agent A - Foundry hosted runtime | `AZURE_AI_ACCOUNT_NAME`, `AZURE_AI_PROJECT_NAME`, `AZURE_AI_PROJECT_ID`, `AZURE_AI_PROJECT_ENDPOINT`, `AZURE_AI_MODEL_DEPLOYMENT_NAME`, `FOUNDRY_RUNTIME_CONNECTION_NAME`, `APPLICATIONINSIGHTS_RESOURCE_ID` |
| Agent C - API/frontend and persistence | `AZURE_API_IDENTITY_CLIENT_ID`, `AZURE_API_IDENTITY_NAME`, `AZURE_WEB_IDENTITY_CLIENT_ID`, `AZURE_POSTGRESQL_HOST`, `AZURE_POSTGRESQL_DATABASE`, `AZURE_POSTGRES_SERVER_NAME`, `AZURE_CONTAINER_REGISTRY_NAME`, `AZURE_CONTAINER_REGISTRY_ENDPOINT`, `AZURE_CONTAINER_APPS_ENVIRONMENT_NAME`, `AZURE_API_CONTAINER_APP_NAME`, `AZURE_API_FQDN`, `AZURE_WEB_CONTAINER_APP_NAME`, `AZURE_WEB_FQDN`, `AZURE_KEY_VAULT_NAME` |
| Agent D - verification and operations | `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`, `APPLICATIONINSIGHTS_RESOURCE_ID`, `LOG_ANALYTICS_WORKSPACE_ID`, API/web names and FQDNs, Foundry project endpoint, and model deployment name |

Application, workflow checkpoint, conversation/session, business state, and
human approval remain separate contracts. These outputs do not authenticate a
person, prove a deployment, or establish production readiness.

## Validation evidence and remaining limits

Local non-deploying evidence:

- `pwsh ./scripts/azure/validate.ps1`: Bicep build and lint succeeded; 8
  infrastructure contract tests passed.
- PowerShell parser validation passed for every `scripts/azure/*.ps1` file.
- `python -m compileall -q ./scripts/azure ./infra/tests` passed.
- `python -m unittest discover -s tests -v`: 68 tests passed with 2 expected
  adapter-not-selected skips.
- The preflight was executed against the current identities and rejected the
  az/azd account-or-tenant mismatch as designed.
- Azure validation did not advance to provider what-if because azd identity is
  mismatched and required deployment parameters are intentionally unset.

Not verified by this workstream: resource provisioning, Azure RBAC writes,
Container Apps image deployment, Hosted Agent creation/invocation, PostgreSQL
connectivity/migration/restore, telemetry ingestion, browser execution,
evaluation quality, rollback in Azure, teardown, or production readiness.

The prepared Container Apps settings satisfy the existing configuration names
(`ENTRA_*`, `CHECKPOINT_ROOT`, `BLUEPRINT_APPLICATION`, telemetry, and a
passwordless PostgreSQL target URL), but the current application still opens
PostgreSQL directly with a static DSN, supports only its local workflow host,
and ships an nginx proxy for the Compose-only `api:8000` name. Deployment is
therefore intentionally blocked before mutation until Agents A/C replace
those integration points and set the readiness value.

## Cleanup ownership

The azd environment owner is responsible for cost monitoring and cleanup.
Workstream B owns the tagged resource-group teardown path for resources in this
topology only. Agent A owns deletion of hosted agent versions and any
post-deployment principal assignments it adds. Agent C owns application
migration compatibility and durable-data export/retention decisions. Agent D
owns retention of evidence needed before resource deletion. Unrelated Azure
resources must never be included in this teardown. The Entra registrations
have a separate, exact-name/client-ID-confirmed teardown because they are not
resource-group resources.
