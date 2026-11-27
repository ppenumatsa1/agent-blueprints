targetScope = 'subscription'

@minLength(1)
@maxLength(24)
param environmentName string

param resourceGroupName string = 'rg-agent-blueprints-ors-foundry-e2e'

param location string = 'eastus2'

@minLength(36)
@maxLength(36)
param apiEntraClientId string

@minLength(1)
param apiEntraAppIdUri string

@minLength(36)
@maxLength(36)
param spaEntraClientId string

@minLength(36)
@maxLength(36)
param postgresAdministratorObjectId string

@minLength(1)
param postgresAdministratorPrincipalName string

@allowed([
  'Group'
  'ServicePrincipal'
  'User'
])
param postgresAdministratorPrincipalType string = 'Group'

param tags object = {}

param modelDeploymentName string = 'gpt-4.1-mini'
param modelName string = 'gpt-4.1-mini'
param modelVersion string = '2025-04-14'
param modelFormat string = 'OpenAI'

@allowed([
  'GlobalStandard'
])
param modelSkuName string = 'GlobalStandard'

@minValue(1)
@maxValue(100)
param modelCapacity int = 10

param postgresSkuName string = 'Standard_B2s'

@allowed([
  'Burstable'
  'GeneralPurpose'
  'MemoryOptimized'
])
param postgresSkuTier string = 'Burstable'

@minValue(32)
param postgresStorageGb int = 32

@minValue(7)
@maxValue(35)
param postgresBackupRetentionDays int = 7

@minValue(30)
@maxValue(730)
param logRetentionDays int = 30

@minValue(1)
@maxValue(10)
param logDailyQuotaGb int = 1

@minValue(0)
@maxValue(5)
param appMinReplicas int = 0

@minValue(1)
@maxValue(10)
param appMaxReplicas int = 2

@description('Public IPv4 firewall rules for PostgreSQL. Populate only with reviewed operator or workload egress addresses.')
param postgresFirewallRules array = []

@description('Optional Key Vault secret references for the API Container App.')
param apiSecretReferences array = []

@description('Create the Foundry project runtime CustomKeys connection after a reviewed passwordless database URL is available.')
param createRuntimeConnection bool = false

@secure()
param runtimeDatabaseUrl string = ''

param runtimeConnectionName string = 'runtime-postgres'

@description('Explicit HTTPS adapter endpoint for the published Foundry hosted workflow.')
@minLength(9)
param hostedWorkflowEndpoint string

@description('Hosted agent version exposed in privacy-safe telemetry.')
@minLength(1)
@maxLength(128)
param agentVersion string = 'unpublished'

@description('Immutable source/deployment revision exposed in privacy-safe telemetry.')
@minLength(1)
@maxLength(128)
param deploymentRevision string = 'infrastructure-unbound'

@description('Enable bounded, role-protected synthetic acceptance controls.')
param acceptanceMode bool = false

@description('Explicit API image. Existing deployments must pass the current immutable digest.')
@minLength(1)
param apiImage string

@description('Explicit web image. Existing deployments must pass the current immutable digest.')
@minLength(1)
param webImage string

var cleanEnvironmentName = take(toLower(replace(environmentName, '-', '')), 8)
var suffix = take(uniqueString(subscription().id, resourceGroupName), 6)
var prefix = 'ab${cleanEnvironmentName}${suffix}'
var resourceTags = union(tags, {
  'azd-env-name': environmentName
  'managed-by': 'azure-cli-bicep'
  workload: 'agent-blueprints'
})

resource resourceGroup 'Microsoft.Resources/resourceGroups@2025-04-01' = {
  name: resourceGroupName
  location: location
  tags: resourceTags
}

module identities './modules/identities.bicep' = {
  name: 'identities'
  scope: resourceGroup
  params: {
    namePrefix: prefix
    location: location
    tags: resourceTags
  }
}

module observability './modules/observability.bicep' = {
  name: 'observability'
  scope: resourceGroup
  params: {
    namePrefix: prefix
    location: location
    tags: resourceTags
    retentionDays: logRetentionDays
    dailyQuotaGb: logDailyQuotaGb
  }
}

module secrets './modules/secrets.bicep' = {
  name: 'secrets'
  scope: resourceGroup
  params: {
    name: '${prefix}-kv'
    location: location
    tags: resourceTags
    apiPrincipalId: identities.outputs.apiPrincipalId
  }
}

module registry './modules/registry.bicep' = {
  name: 'registry'
  scope: resourceGroup
  params: {
    name: '${prefix}cr'
    location: location
    tags: resourceTags
    apiPrincipalId: identities.outputs.apiPrincipalId
    webPrincipalId: identities.outputs.webPrincipalId
  }
}

module foundry './modules/foundry.bicep' = {
  name: 'foundry'
  scope: resourceGroup
  params: {
    accountName: '${prefix}-foundry'
    projectName: '${prefix}-project'
    location: location
    tags: resourceTags
    applicationInsightsResourceId: observability.outputs.applicationInsightsResourceId
    applicationInsightsConnectionString: observability.outputs.applicationInsightsConnectionString
    modelDeploymentName: modelDeploymentName
    modelName: modelName
    modelVersion: modelVersion
    modelFormat: modelFormat
    modelSkuName: modelSkuName
    modelCapacity: modelCapacity
    createRuntimeConnection: createRuntimeConnection
    runtimeConnectionName: runtimeConnectionName
    runtimeDatabaseUrl: runtimeDatabaseUrl
  }
}

module postgres './modules/postgres.bicep' = {
  name: 'postgres'
  scope: resourceGroup
  params: {
    name: '${prefix}-pg'
    location: location
    tags: resourceTags
    administratorObjectId: postgresAdministratorObjectId
    administratorPrincipalName: postgresAdministratorPrincipalName
    administratorPrincipalType: postgresAdministratorPrincipalType
    skuName: postgresSkuName
    skuTier: postgresSkuTier
    storageGb: postgresStorageGb
    backupRetentionDays: postgresBackupRetentionDays
    firewallRules: postgresFirewallRules
  }
}

module containerApps './modules/container-apps.bicep' = {
  name: 'container-apps'
  scope: resourceGroup
  params: {
    namePrefix: prefix
    location: location
    tags: resourceTags
    workspaceName: observability.outputs.workspaceName
    apiIdentityId: identities.outputs.apiIdentityId
    apiIdentityClientId: identities.outputs.apiClientId
    apiIdentityName: identities.outputs.apiName
    webIdentityId: identities.outputs.webIdentityId
    apiEntraClientId: apiEntraClientId
    apiEntraAppIdUri: apiEntraAppIdUri
    registryServer: registry.outputs.loginServer
    keyVaultName: secrets.outputs.name
    apiSecretReferences: apiSecretReferences
    applicationInsightsConnectionString: observability.outputs.applicationInsightsConnectionString
    foundryProjectEndpoint: foundry.outputs.projectEndpoint
    modelDeploymentName: modelDeploymentName
    postgresHost: postgres.outputs.fqdn
    postgresDatabaseName: postgres.outputs.databaseName
    hostedWorkflowEndpoint: hostedWorkflowEndpoint
    agentVersion: agentVersion
    deploymentRevision: deploymentRevision
    acceptanceMode: acceptanceMode
    minReplicas: appMinReplicas
    maxReplicas: appMaxReplicas
    apiImage: apiImage
    webImage: webImage
  }
}

module telemetryRole './modules/role-assignment.bicep' = {
  name: 'api-telemetry-role'
  scope: resourceGroup
  params: {
    applicationInsightsName: observability.outputs.applicationInsightsName
    principalId: identities.outputs.apiPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '3913510d-42f4-4e42-8a64-420c390055eb'
    )
    assignmentSeed: 'api-monitoring-metrics-publisher'
  }
}

module foundryTelemetryRole './modules/role-assignment.bicep' = {
  name: 'foundry-project-telemetry-role'
  scope: resourceGroup
  params: {
    applicationInsightsName: observability.outputs.applicationInsightsName
    principalId: foundry.outputs.projectPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '3913510d-42f4-4e42-8a64-420c390055eb'
    )
    assignmentSeed: 'foundry-project-monitoring-metrics-publisher'
  }
}

output AZURE_RESOURCE_GROUP string = resourceGroup.name
output AZURE_LOCATION string = location
output AZURE_AI_ACCOUNT_NAME string = foundry.outputs.accountName
output AZURE_AI_PROJECT_NAME string = foundry.outputs.projectName
output AZURE_AI_PROJECT_ID string = foundry.outputs.projectId
output AZURE_AI_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
output AZURE_AI_MODEL_DEPLOYMENT_NAME string = modelDeploymentName
output AZURE_API_ENTRA_CLIENT_ID string = apiEntraClientId
output AZURE_API_ENTRA_APP_ID_URI string = apiEntraAppIdUri
output AZURE_SPA_ENTRA_CLIENT_ID string = spaEntraClientId
output AZURE_API_IDENTITY_CLIENT_ID string = identities.outputs.apiClientId
output AZURE_API_IDENTITY_NAME string = identities.outputs.apiName
output AZURE_API_IDENTITY_PRINCIPAL_ID string = identities.outputs.apiPrincipalId
output AZURE_WEB_IDENTITY_CLIENT_ID string = identities.outputs.webClientId
output AZURE_WEB_IDENTITY_PRINCIPAL_ID string = identities.outputs.webPrincipalId
output AZURE_POSTGRESQL_HOST string = postgres.outputs.fqdn
output AZURE_POSTGRESQL_DATABASE string = postgres.outputs.databaseName
output AZURE_POSTGRES_SERVER_NAME string = postgres.outputs.name
output AZURE_CONTAINER_REGISTRY_NAME string = registry.outputs.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output AZURE_CONTAINER_APPS_ENVIRONMENT_NAME string = containerApps.outputs.environmentName
output AZURE_API_CONTAINER_APP_NAME string = containerApps.outputs.apiName
output AZURE_API_FQDN string = containerApps.outputs.apiFqdn
output AZURE_WEB_CONTAINER_APP_NAME string = containerApps.outputs.webName
output AZURE_WEB_FQDN string = containerApps.outputs.webFqdn
output AZURE_KEY_VAULT_NAME string = secrets.outputs.name
output APPLICATIONINSIGHTS_RESOURCE_ID string = observability.outputs.applicationInsightsResourceId
output LOG_ANALYTICS_WORKSPACE_ID string = observability.outputs.workspaceResourceId
output FOUNDRY_RUNTIME_CONNECTION_NAME string = createRuntimeConnection ? runtimeConnectionName : ''
output AGENT_VERSION string = agentVersion
output DEPLOYMENT_REVISION string = deploymentRevision
output ACCEPTANCE_MODE string = string(acceptanceMode)
