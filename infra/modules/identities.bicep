targetScope = 'resourceGroup'

param namePrefix string
param location string
param tags object

module api 'br/public:avm/res/managed-identity/user-assigned-identity:0.6.0' = {
  name: 'api-identity'
  params: {
    name: '${namePrefix}-api-id'
    location: location
    tags: tags
  }
}

module web 'br/public:avm/res/managed-identity/user-assigned-identity:0.6.0' = {
  name: 'web-identity'
  params: {
    name: '${namePrefix}-web-id'
    location: location
    tags: tags
  }
}

output apiIdentityId string = api.outputs.resourceId
output apiName string = api.outputs.name
output apiClientId string = api.outputs.clientId
output apiPrincipalId string = api.outputs.principalId
output webIdentityId string = web.outputs.resourceId
output webName string = web.outputs.name
output webClientId string = web.outputs.clientId
output webPrincipalId string = web.outputs.principalId
