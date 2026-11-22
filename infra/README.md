# Azure/Foundry infrastructure

This root deployment surface provisions the public Azure resources and deploys
an independently generated Order Resolution application. It never deploys
`blueprints/maf/workflow` as the cloud application.

## Deployment shape

- Microsoft Foundry account, project, and explicit model deployment
- generated Foundry Hosted Agent source published with the Agent A SDK fallback
- generated API and frontend deployed to public Azure Container Apps
- Basic ACR for generated API/frontend images only
- PostgreSQL Flexible Server with Entra-only authentication and TLS verification
- user-assigned managed identities and scoped RBAC
- Key Vault, Log Analytics, and Application Insights

No virtual network, private endpoint, private DNS zone, private runner,
password-authenticated database, local workflow host, or file checkpoint root
is created.

## Local validation

```powershell
.\scripts\azure\validate.ps1
```

The command builds and lints Bicep and runs non-deploying infrastructure
contracts, including identity-mode and generated-application deployment
contracts.

## Read-only Azure preflight

Azure CLI mode is the supported deployment route. It validates the active
Azure CLI context without changing the active subscription:

```powershell
.\scripts\azure\preflight.ps1 `
  -DeploymentMode AzureCli `
  -SubscriptionId '<subscription-guid>' `
  -TenantId '<tenant-guid>' `
  -ExpectedUser '<user-principal-name>' `
  -Location eastus2
```

An azd mismatch is reported but does not block Azure CLI mode. Optional azd
mode remains fail-closed and must be selected explicitly:

```powershell
.\scripts\azure\preflight.ps1 -DeploymentMode Azd -FromAzdEnvironment
```

Both modes check effective roles, provider registration, exact-region resource
support, model catalog/SKU/capabilities, platform capacity, subscription quota,
PostgreSQL SKU, and Container Apps quota. Region fallback is never automatic.

## Generated hosted composition

`deploy.ps1` creates a new temporary directory and runs:

```powershell
python scripts\instantiate_maf.py --profile order-resolution <new-temp-path>
```

Before any Azure mutation it requires generated `backend`, `frontend`,
`hosted-agent`, and publisher paths. The generated frontend nginx configuration
must contain the known Compose upstream; deployment replaces that copy with the
exact HTTPS API FQDN before the image build. Source files in this repository are
not patched or used as runtime dependencies.

The API ACR build stages only Agent A's API-side `client.py` and `bridge.py`
modules into Agent C's generated backend with a side-effect-free package
initializer. `infra/docker/order-resolution-api.Dockerfile` then builds from
that backend context only. Hosted-agent source remains separately publishable;
the API does not depend on sibling `PYTHONPATH` configuration or install/import
the full hosted runtime.

Before any live deployment, validate the composed generated image locally:

```powershell
pwsh ./scripts/azure/test-generated-api-image.ps1 `
  -GeneratedProjectRoot <composed-generated-root>
```

The API is configured only for `WORKFLOW_HOST=hosted`,
`HOSTED_WORKFLOW_ENDPOINT`, the `https://ai.azure.com/.default` scope,
managed-identity PostgreSQL, TLS `verify-full`, Entra, and Azure Monitor. It
uses the trusted system CA store and does not receive `BLUEPRINT_APPLICATION`
or `CHECKPOINT_ROOT`.

The hosted definition receives only the Foundry project/model settings plus
`ORDER_RESOLUTION_API_ENDPOINT`, `ORDER_RESOLUTION_API_SCOPE`, and a 30-second
API timeout. It receives no database configuration or credentials.

## What-if

Use an ARM deployment parameter file with concrete reviewed values:

```powershell
.\scripts\azure\what-if.ps1 `
  -Location eastus2 `
  -ParameterFile '<resolved-parameters.json>' `
  -SubscriptionId '<subscription-guid>' `
  -TenantId '<tenant-guid>' `
  -ExpectedUser '<user-principal-name>'
```

What-if is non-deploying and uses the verified Azure CLI context.

## Deployment

Deployment is disabled unless `-Apply` is supplied. Required values are
explicit; the command does not infer a hosted endpoint, agent name, directory
administrator, or publish operation:

```powershell
.\scripts\azure\deploy.ps1 `
  -Apply `
  -DeploymentMode AzureCli `
  -OperatorIp '<current-public-ipv4>' `
  -EnvironmentName '<environment>' `
  -SubscriptionId '<subscription-guid>' `
  -TenantId '<tenant-guid>' `
  -ExpectedUser '<user-principal-name>' `
  -PostgresAdministratorObjectId '<entra-object-guid>' `
  -PostgresAdministratorPrincipalName '<entra-principal-name>' `
  -HostedWorkflowEndpoint '<https-adapter-endpoint>' `
  -HostedResponsesEndpoint '<https-responses-endpoint>' `
  -HostedConversationEndpoint '<https-conversation-endpoint>' `
  -HostedAgentName '<agent-name>' `
  -HostedPublishOperationId '<stable-operation-id>' `
  -HostedPublishJournal '<durable-journal-path>' `
  -OutputsFile '<deployment-values.json>'
```

The orchestrator:

1. generates and validates an independent Order Resolution project;
2. validates Azure CLI identity, permissions, providers, region, quota, and
   capacity while reporting but not blocking on an unrelated azd identity;
3. creates/reuses the single-tenant API and SPA registrations without secrets;
4. runs provider-backed subscription what-if and Bicep deployment;
5. reconciles only the exact API Container App PostgreSQL egress rules, creates
   the API database principal, runs migrations, and deploys the protected API
   bootstrap/internal hosted-state boundary in hosted mode. Its temporary
   service identity is the credentialless API resource service principal,
   which has no `Hosted.Workflow.Invoke` assignment and therefore fails closed;
6. publishes generated hosted source configured with that API endpoint/scope
   and captures the authoritative
   version identity while its provisioning status may still be `creating`;
7. grants the API UAMI `Foundry Agent Consumer` and assigns the dedicated
   `Hosted.Workflow.Invoke` API application role to the hosted principal, but
   only at the exact agent scope derived from the validated project resource ID
   and the same fixed agent name passed to the publisher;
8. reruns the identical journaled publisher operation with `--require-active`,
   which performs no create and verifies the same version identity is active;
9. binds the API to the authoritative hosted principal and final Foundry
   endpoints, builds the generated frontend context in ACR, resolves immutable
   image digests, updates Container Apps, records outputs/revisions, and
   verifies health and cloud runtime configuration.

The operator firewall rule exists only inside self-cleaning `try/finally`
scopes. Only API Container App outbound addresses are reconciled; a changed
address fails database access closed until reconciliation. Foundry hosted code
receives no database URL, credential, role, or firewall rule and reaches
business state only through the protected API. The broad Azure-services
`0.0.0.0` exception is never used.

`-DeploymentMode Azd` validates the azd identity but intentionally refuses app
deployment because root `azure.yaml` is infrastructure-only and cannot target a
generated temporary project.

## Rollback and teardown

Rollback uses exact prior revisions whose images are immutable digests:

```powershell
.\scripts\azure\rollback.ps1 -Apply `
  -DeploymentMode AzureCli `
  -ValuesFile '<deployment-values.json>' `
  -ApiRevision '<api-revision>' `
  -WebRevision '<web-revision>'
```

Hosted Agent versions are immutable. Reconcile ambiguous publishes before any
retry; otherwise publish a reviewed replacement version rather than overwriting
evidence.

No RBAC scope input is accepted. `deploy.ps1` derives the official
`<project-resource-id>/agents/<agent-name>` scope from validated outputs and
the fixed publisher name. Project, account, resource-group, subscription,
agent-version, role-assignment, and another-agent scopes are prohibited.

Resource teardown is destructive, never automatic, and checks both the exact
environment name and ownership tag:

```powershell
.\scripts\azure\teardown.ps1 -Apply `
  -DeploymentMode AzureCli `
  -ValuesFile '<deployment-values.json>' `
  -ConfirmEnvironmentName '<environment>'
```

Entra applications and service principals are outside resource-group teardown
and require the separate exact-name/client-ID-confirmed
`teardown-entra.ps1` operation. It removes the API/SPA identities and
registrations but never deletes the platform hosted principal.
