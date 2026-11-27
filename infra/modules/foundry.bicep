targetScope = 'resourceGroup'

param accountName string
param projectName string
param location string
param tags object
param applicationInsightsResourceId string

@secure()
param applicationInsightsConnectionString string

param modelDeploymentName string
param modelName string
param modelVersion string
param modelFormat string
param modelSkuName string
param modelCapacity int
param createRuntimeConnection bool
param runtimeConnectionName string

@secure()
param runtimeDatabaseUrl string

var cognitiveServicesOpenAIUserRole = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
)

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'S0'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource model 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: modelDeploymentName
  sku: {
    name: modelSkuName
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: modelFormat
      name: modelName
      version: modelVersion
    }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: 'Public-network Microsoft Agent Framework workflow project'
    displayName: projectName
  }
  dependsOn: [
    model
  ]
}

resource projectOpenAIUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, project.id, cognitiveServicesOpenAIUserRole)
  scope: account
  properties: {
    roleDefinitionId: cognitiveServicesOpenAIUserRole
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource applicationInsightsConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = {
  parent: project
  name: 'ApplicationInsights'
  properties: {
    #disable-next-line BCP036
    authType: 'ProjectManagedIdentity'
    category: 'AppInsights'
    isSharedToAll: false
    metadata: {
      ApiType: 'Azure'
      ApplicationInsightsConnectionString: applicationInsightsConnectionString
      ResourceId: applicationInsightsResourceId
      location: location
    }
    target: applicationInsightsResourceId
  }
}

resource runtimeSecretConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01' = if (createRuntimeConnection) {
  parent: project
  name: runtimeConnectionName
  properties: {
    authType: 'CustomKeys'
    category: 'CustomKeys'
    credentials: {
      keys: {
        database_url: runtimeDatabaseUrl
      }
    }
    isSharedToAll: false
    metadata: {
      ApiType: 'KeyValue'
      location: location
    }
    target: 'https://runtime-secrets.invalid'
  }
}

output accountName string = account.name
output accountId string = account.id
output projectName string = project.name
output projectId string = project.id
output projectEndpoint string = project.properties.endpoints['AI Foundry API']
output projectPrincipalId string = project.identity.principalId
output modelDeploymentName string = model.name
output runtimeConnectionName string = createRuntimeConnection ? runtimeSecretConnection!.name : ''
