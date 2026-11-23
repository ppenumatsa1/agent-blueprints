targetScope = 'resourceGroup'

param name string
param location string
param tags object
param administratorObjectId string
param administratorPrincipalName string

@allowed([
  'Group'
  'ServicePrincipal'
  'User'
])
param administratorPrincipalType string

param databaseName string = 'workflow'
param skuName string
param skuTier string
param storageGb int
param backupRetentionDays int
param firewallRules array

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2025-08-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    authConfig: {
      activeDirectoryAuth: 'Enabled'
      passwordAuth: 'Disabled'
      tenantId: tenant().tenantId
    }
    backup: {
      backupRetentionDays: backupRetentionDays
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
    storage: {
      autoGrow: 'Enabled'
      storageSizeGB: storageGb
    }
    version: '17'
  }
}

resource administrator 'Microsoft.DBforPostgreSQL/flexibleServers/administrators@2025-08-01' = {
  parent: server
  name: administratorObjectId
  properties: {
    principalName: administratorPrincipalName
    principalType: administratorPrincipalType
    tenantId: tenant().tenantId
  }
}

resource requireTls 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2025-08-01' = {
  parent: server
  name: 'require_secure_transport'
  properties: {
    source: 'user-override'
    value: 'ON'
  }
  dependsOn: [
    administrator
  ]
}

resource minimumTls 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2025-08-01' = {
  parent: server
  name: 'ssl_min_protocol_version'
  properties: {
    source: 'user-override'
    value: 'TLSv1.2'
  }
  dependsOn: [
    requireTls
  ]
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2025-08-01' = {
  parent: server
  name: databaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
  dependsOn: [
    minimumTls
  ]
}

resource publicFirewallRules 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2025-08-01' = [
  for rule in firewallRules: {
    parent: server
    name: rule.name
    properties: {
      endIpAddress: rule.endIpAddress
      startIpAddress: rule.startIpAddress
    }
    dependsOn: [
      database
    ]
  }
]

output id string = server.id
output name string = server.name
output fqdn string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
