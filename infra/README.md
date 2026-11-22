# Azure/Foundry infrastructure

This root deployment surface prepares the MAF workflow blueprint for a public
Azure milestone. It is separate from the blueprint-local historical staging
templates under `blueprints/maf/workflow/infra/`.

## Deployment shape

- Microsoft Foundry account, project, and one explicit model deployment
- code-deployed Hosted Agent integration contract (agent source is supplied by
  the runtime workstream)
- public Azure Container Apps API and frontend
- Basic Azure Container Registry for API/frontend images only
- PostgreSQL Flexible Server with Entra-only authentication
- user-assigned managed identities and scoped RBAC
- Key Vault, Log Analytics, and Application Insights

No virtual network, private endpoint, private DNS zone, private runner, or
password-authenticated database is created.

## Local validation

```powershell
.\scripts\azure\validate.ps1
```

The command builds and lints Bicep and runs non-deploying infrastructure
contract tests. It does not contact Azure except to restore public AVM modules
when they are not already cached.

## Read-only Azure preflight

Set the authorized values in the selected azd environment:

```powershell
azd env set AZURE_SUBSCRIPTION_ID '<subscription-guid>'
azd env set AZURE_TENANT_ID '<tenant-guid>'
azd env set AZURE_EXPECTED_USER '<user-principal-name>'
azd env set AZURE_LOCATION 'eastus2'
```

Then run:

```powershell
.\scripts\azure\preflight.ps1 -FromAzdEnvironment
```

The preflight never calls `az account set`. It verifies Azure CLI and azd
account/tenant match, checks effective roles and provider registration, and
evaluates the exact `AZURE_LOCATION` for resource support, model catalog/SKU,
platform capacity, subscription quota, PostgreSQL SKU, and Container Apps
environment quota. Changing region is a separate reviewed environment change,
not an automatic fallback.

## Entra application setup

The API and SPA registrations are deployment-time directory objects, not Bicep
resources. Validate the deterministic names without mutation:

```powershell
.\scripts\azure\configure-entra.ps1
```

After az and azd use the same authorized account and tenant, create or
idempotently reconcile the single-tenant registrations:

```powershell
.\scripts\azure\configure-entra.ps1 -Apply
```

The script exposes `workflow.read`, `workflow.write`, and `workflow.approve`,
defines `Workflow.User` and `Workflow.Approver`, configures only localhost SPA
redirects until the deployed FQDN is known, and stores client IDs/app ID URI in
the selected azd environment. It creates no secret and no test user. Directory
permissions to create/update applications are a separate prerequisite from
Azure subscription roles.

## What-if

Use the reviewed environment parameter file:

```powershell
.\scripts\azure\what-if.ps1 `
  -Location eastus2 `
  -ParameterFile .\infra\environments\dev.bicepparam
```

What-if is non-deploying but contacts Azure and can expose proposed resource
names. Do not use the checked-in example GUIDs for a real preview.

## Deployment and configuration

Deployment is deliberately disabled unless `-Apply` is supplied:

```powershell
.\scripts\azure\deploy.ps1 -Apply -OperatorIp '<current-public-ipv4>'
```

Deployment also requires `AZURE_APPLICATION_RUNTIME_READY=true`. Agents A and
C may set it only after the backend uses managed-identity PostgreSQL token
acquisition, the hosted-runtime adapter is selected, and the frontend proxy
resolves the deployed API rather than the Compose-only `api:8000` name. The
current base intentionally remains blocked.

The orchestrator runs the identity/capacity preflight, `azd provision`,
PostgreSQL firewall and managed-identity principal configuration, schema-owner
migrations, `azd deploy`, and exact health/revision verification. The supplied
operator IPv4 address is separately allowlisted only inside configuration and
migration `try/finally` scopes and is removed even when either operation fails.
It also reconciles the Entra registrations before provision and adds the exact
deployed frontend origin afterward.

The API Container App's current outbound IP set is allowlisted on PostgreSQL
after provisioning. Consumption outbound addresses are not a permanent
network identity; re-run the configuration step after any app/environment
change that can alter them. If an address changes before reconciliation,
database traffic fails closed. The script reconciles only its
`container-apps-*` rules and removes stale managed entries. Public PostgreSQL
access remains blocked for other IPs; the broad Azure-services `0.0.0.0` rule
is not used.

Hosted Agent code deployment is added by the runtime workstream as an
`azure.ai.agent` service. Do not change it to container mode or grant the
Foundry project ACR access unless a verified technical requirement is recorded.

## Rollback and teardown

Rollback creates new Container Apps revisions from reviewed immutable image
digests:

```powershell
.\scripts\azure\rollback.ps1 -Apply `
  -ApiRevision '<api-revision>' `
  -WebRevision '<web-revision>'
```

Hosted Agent versions are immutable. Roll back by redeploying the reviewed
source revision as a new version and updating the consumer-selected version;
do not overwrite evidence for the failed version.

Teardown is destructive, never automatic, and requires the exact selected
environment name:

```powershell
.\scripts\azure\teardown.ps1 -Apply -ConfirmEnvironmentName '<environment>'
```

The script verifies the resource group's `azd-env-name` tag before invoking
`azd down --purge --force`.

Entra applications are intentionally outside resource-group teardown. Delete
them only with separate exact-name and app-ID confirmation:

```powershell
.\scripts\azure\teardown-entra.ps1 -Apply `
  -ConfirmApiDisplayName 'agent-blueprints-order-resolution-api' `
  -ConfirmSpaDisplayName 'agent-blueprints-order-resolution-spa'
```
