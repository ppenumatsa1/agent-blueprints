targetScope = 'resourceGroup'

param name string
param location string
param tags object
param projectName string
param apiPrincipalId string
param grantProjectAgentConsumer bool = false
param deployModel bool = false
param modelDeploymentName string = ''
param modelName string = ''
param modelVersion string = ''
param modelFormat string = 'OpenAI'
param modelSku string = 'Standard'

@minValue(1)
param modelCapacity int = 1

var foundryAgentConsumerRole = 'eed3b665-ab3a-47b6-8f48-c9382fb1dad6'
var foundryUserRole = '53ca6127-db72-4b80-b1b0-d745d6d5456d'

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: name
  location: location
  kind: 'AIServices'
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'S0'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: name
    disableLocalAuth: true
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      defaultAction: 'Deny'
      ipRules: []
      virtualNetworkRules: []
    }
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
    displayName: projectName
  }
}

resource model 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = if (deployModel) {
  parent: account
  name: modelDeploymentName
  sku: {
    name: modelSku
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: modelFormat
      name: modelName
      version: modelVersion
    }
  }
}

resource consumerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (grantProjectAgentConsumer) {
  name: guid(project.id, apiPrincipalId, foundryAgentConsumerRole)
  scope: project
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryAgentConsumerRole)
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource projectRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, project.id, foundryUserRole)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryUserRole)
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output accountName string = account.name
output projectName string = project.name
output projectId string = project.id
output projectEndpoint string = project.properties.endpoints['AI Foundry API']
