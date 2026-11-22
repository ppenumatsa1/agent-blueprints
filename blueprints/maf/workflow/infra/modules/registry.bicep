targetScope = 'resourceGroup'

param name string
param location string
param tags object
param apiPrincipalId string
param webPrincipalId string

@allowed([
  'Basic'
  'Standard'
  'Premium'
])
param skuName string = 'Basic'

var acrPullRole = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource registry 'Microsoft.ContainerRegistry/registries@2025-04-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource apiPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, apiPrincipalId, acrPullRole)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRole)
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
  }
}

resource webPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, webPrincipalId, acrPullRole)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRole)
    principalId: webPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output loginServer string = registry.properties.loginServer
