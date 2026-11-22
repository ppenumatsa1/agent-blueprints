targetScope = 'resourceGroup'

param applicationInsightsName string
param principalId string

@allowed([
  'Device'
  'ForeignGroup'
  'Group'
  'ServicePrincipal'
  'User'
])
param principalType string

param roleDefinitionId string
param assignmentSeed string

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: applicationInsightsName
}

resource assignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(applicationInsights.id, principalId, roleDefinitionId, assignmentSeed)
  scope: applicationInsights
  properties: {
    roleDefinitionId: roleDefinitionId
    principalId: principalId
    principalType: principalType
  }
}

output id string = assignment.id
