targetScope = 'resourceGroup'

param name string
param location string
param tags object
param addressPrefix string = '10.42.0.0/16'
param appsSubnetPrefix string = '10.42.0.0/23'
param databaseSubnetPrefix string = '10.42.2.0/24'

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        addressPrefix
      ]
    }
  }
}

resource appsSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: vnet
  name: 'apps'
  properties: {
    addressPrefix: appsSubnetPrefix
    delegations: [
      {
        name: 'container-apps'
        properties: {
          serviceName: 'Microsoft.App/environments'
        }
      }
    ]
  }
}

resource databaseSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: vnet
  name: 'postgres'
  properties: {
    addressPrefix: databaseSubnetPrefix
    delegations: [
      {
        name: 'postgres'
        properties: {
          serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers'
        }
      }
    ]
  }
}

resource databaseDns 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: '${name}.postgres.database.azure.com'
  location: 'global'
  tags: tags
}

resource databaseDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: databaseDns
  name: 'database-network'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

output appsSubnetId string = appsSubnet.id
output databaseSubnetId string = databaseSubnet.id
output databaseDnsZoneId string = databaseDns.id
