targetScope = 'subscription'

@minLength(1)
@maxLength(30)
param environmentName string

param location string

@minLength(36)
@maxLength(36)
param postgresAdministratorObjectId string

@minLength(1)
param postgresAdministratorPrincipalName string

@minLength(36)
@maxLength(36)
param apiEntraClientId string

@allowed([
  'Group'
  'ServicePrincipal'
  'User'
])
param postgresAdministratorPrincipalType string = 'Group'

param tags object = {}
param networkAddressPrefix string = '10.42.0.0/16'
param appsSubnetPrefix string = '10.42.0.0/23'
param postgresSubnetPrefix string = '10.42.2.0/24'
param postgresSkuName string = 'Standard_B1ms'
param postgresSkuTier string = 'Burstable'
param postgresStorageGb int = 32
param postgresBackupRetentionDays int = 7
param logRetentionDays int = 30
param logDailyQuotaGb int = 1

@description('Model deployment is opt-in; its name, version, SKU, capacity and regional quota require review.')
param deployModel bool = false
param modelDeploymentName string = ''
param modelName string = ''
param modelVersion string = ''
param modelFormat string = 'OpenAI'
param modelSku string = 'Standard'
param modelCapacity int = 1

@description('Opt-in grants API access to all agents in the project; prefer a verified agent-scoped assignment.')
param grantProjectAgentConsumer bool = false

@description('An authenticated public-network registry is created only when explicitly selected.')
param createRegistry bool = false
param registrySku string = 'Basic'

@description('The private UI/API containers are disabled until their image and host contracts are reviewed.')
param createContainerApps bool = false
param apiImage string = ''
param webImage string = ''
param apiEnvironment array = []
param apiSecretReferences array = []
param webEnvironment array = []

var suffix = uniqueString(subscription().id, environmentName, location)
var prefix = 'maf${suffix}'
var resourceTags = union(tags, {
  'azd-env-name': environmentName
})

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: resourceTags
}

module network './modules/network.bicep' = {
  name: 'network'
  scope: resourceGroup
  params: {
    name: '${prefix}-net'
    location: location
    tags: resourceTags
    addressPrefix: networkAddressPrefix
    appsSubnetPrefix: appsSubnetPrefix
    databaseSubnetPrefix: postgresSubnetPrefix
  }
}

module identities './modules/identities.bicep' = {
  name: 'identities'
  scope: resourceGroup
  params: {
    name: prefix
    location: location
    tags: resourceTags
  }
}

module observability './modules/observability.bicep' = {
  name: 'observability'
  scope: resourceGroup
  params: {
    name: prefix
    location: location
    tags: resourceTags
    retentionDays: logRetentionDays
    dailyQuotaGb: logDailyQuotaGb
  }
}

module foundry './modules/foundry.bicep' = {
  name: 'foundry'
  scope: resourceGroup
  params: {
    name: '${prefix}-ai'
    location: location
    tags: resourceTags
    projectName: '${prefix}-project'
    apiPrincipalId: identities.outputs.apiPrincipalId
    grantProjectAgentConsumer: grantProjectAgentConsumer
    deployModel: deployModel
    modelDeploymentName: modelDeploymentName
    modelName: modelName
    modelVersion: modelVersion
    modelFormat: modelFormat
    modelSku: modelSku
    modelCapacity: modelCapacity
  }
}

module postgres './modules/postgres.bicep' = {
  name: 'postgres'
  scope: resourceGroup
  params: {
    name: '${prefix}-db'
    location: location
    tags: resourceTags
    delegatedSubnetId: network.outputs.databaseSubnetId
    privateDnsZoneId: network.outputs.databaseDnsZoneId
    administratorObjectId: postgresAdministratorObjectId
    administratorPrincipalName: postgresAdministratorPrincipalName
    administratorPrincipalType: postgresAdministratorPrincipalType
    skuName: postgresSkuName
    skuTier: postgresSkuTier
    storageGb: postgresStorageGb
    backupRetentionDays: postgresBackupRetentionDays
  }
}

module registry './modules/registry.bicep' = if (createRegistry) {
  name: 'registry'
  scope: resourceGroup
  params: {
    name: 'cr${suffix}'
    location: location
    tags: resourceTags
    apiPrincipalId: identities.outputs.apiPrincipalId
    webPrincipalId: identities.outputs.webPrincipalId
    skuName: registrySku
  }
}

module containerApps './modules/container-apps.bicep' = if (createContainerApps) {
  name: 'container-apps'
  scope: resourceGroup
  params: {
    name: prefix
    location: location
    tags: resourceTags
    subnetId: network.outputs.appsSubnetId
    workspaceName: observability.outputs.workspaceName
    apiIdentityId: identities.outputs.apiId
    webIdentityId: identities.outputs.webId
    apiImage: apiImage
    webImage: webImage
    apiEntraClientId: apiEntraClientId
    registryServer: createRegistry ? registry!.outputs.loginServer : ''
    apiEnvironment: apiEnvironment
    apiSecretReferences: apiSecretReferences
    webEnvironment: webEnvironment
  }
}

output AZURE_RESOURCE_GROUP string = resourceGroup.name
output AZURE_AI_ACCOUNT_NAME string = foundry.outputs.accountName
output AZURE_AI_PROJECT_NAME string = foundry.outputs.projectName
output AZURE_AI_PROJECT_ID string = foundry.outputs.projectId
output AZURE_AI_PROJECT_ENDPOINT string = foundry.outputs.projectEndpoint
output AZURE_AI_MODEL_DEPLOYMENT_NAME string = deployModel ? modelDeploymentName : ''
output AZURE_POSTGRESQL_HOST string = postgres.outputs.host
output AZURE_POSTGRESQL_DATABASE string = postgres.outputs.databaseName
output AZURE_API_IDENTITY_CLIENT_ID string = identities.outputs.apiClientId
output AZURE_LOG_ANALYTICS_WORKSPACE_ID string = observability.outputs.workspaceId
output AZURE_APPLICATION_INSIGHTS_ID string = observability.outputs.insightsId
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = createRegistry ? registry!.outputs.loginServer : ''
output API_PRIVATE_FQDN string = createContainerApps ? containerApps!.outputs.apiFqdn : ''
output WEB_PRIVATE_FQDN string = createContainerApps ? containerApps!.outputs.webFqdn : ''
