targetScope = 'resourceGroup'

param name string
param location string
param tags object
param apiPrincipalId string
param webPrincipalId string

module registry 'br/public:avm/res/container-registry/registry:0.13.2' = {
  name: 'container-registry'
  params: {
    name: name
    location: location
    acrSku: 'Basic'
    acrAdminUserEnabled: false
    anonymousPullEnabled: false
    publicNetworkAccess: 'Enabled'
    roleAssignments: [
      {
        principalId: apiPrincipalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: 'AcrPull'
      }
      {
        principalId: webPrincipalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: 'AcrPull'
      }
    ]
    tags: tags
  }
}

output name string = name
output resourceId string = registry.outputs.resourceId
output loginServer string = registry.outputs.loginServer
