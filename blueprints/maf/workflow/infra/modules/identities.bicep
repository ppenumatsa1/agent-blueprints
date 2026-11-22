targetScope = 'resourceGroup'

param name string
param location string
param tags object

resource apiIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${name}-api'
  location: location
  tags: tags
}

resource webIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${name}-web'
  location: location
  tags: tags
}

output apiId string = apiIdentity.id
output apiClientId string = apiIdentity.properties.clientId
output apiPrincipalId string = apiIdentity.properties.principalId
output webId string = webIdentity.id
output webPrincipalId string = webIdentity.properties.principalId
