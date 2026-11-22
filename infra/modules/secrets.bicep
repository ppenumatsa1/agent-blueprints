targetScope = 'resourceGroup'

param name string
param location string
param tags object
param apiPrincipalId string

var keyVaultSecretsUserRole = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4633458b-17de-408a-b874-0445c86b69e6'
)

resource vault 'Microsoft.KeyVault/vaults@2025-05-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    enableRbacAuthorization: true
    enablePurgeProtection: true
    enableSoftDelete: true
    publicNetworkAccess: 'Enabled'
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: tenant().tenantId
  }
}

resource apiSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vault.id, apiPrincipalId, keyVaultSecretsUserRole)
  scope: vault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRole
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output name string = vault.name
output resourceId string = vault.id
output uri string = vault.properties.vaultUri
