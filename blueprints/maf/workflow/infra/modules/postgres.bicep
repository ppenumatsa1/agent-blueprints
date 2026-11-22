targetScope = 'resourceGroup'

param name string
param location string
param tags object
param delegatedSubnetId string
param privateDnsZoneId string
param administratorObjectId string
param administratorPrincipalName string

@allowed([
  'Group'
  'ServicePrincipal'
  'User'
])
param administratorPrincipalType string = 'Group'

param databaseName string = 'workflow'
param skuName string = 'Standard_B1ms'

@allowed([
  'Burstable'
  'GeneralPurpose'
  'MemoryOptimized'
])
param skuTier string = 'Burstable'

@minValue(32)
param storageGb int = 32

@minValue(7)
@maxValue(35)
param backupRetentionDays int = 7

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    version: '16'
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Disabled'
      tenantId: tenant().tenantId
    }
    network: {
      delegatedSubnetResourceId: delegatedSubnetId
      privateDnsZoneArmResourceId: privateDnsZoneId
      publicNetworkAccess: 'Disabled'
    }
    storage: {
      storageSizeGB: storageGb
    }
    backup: {
      backupRetentionDays: backupRetentionDays
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

resource administrator 'Microsoft.DBforPostgreSQL/flexibleServers/administrators@2024-08-01' = {
  parent: server
  name: administratorObjectId
  properties: {
    principalName: administratorPrincipalName
    principalType: administratorPrincipalType
    tenantId: tenant().tenantId
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: server
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource requireTls 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: server
  name: 'require_secure_transport'
  properties: {
    source: 'user-override'
    value: 'ON'
  }
}

output host string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
output id string = server.id
