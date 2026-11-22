targetScope = 'resourceGroup'

param name string
param location string
param tags object

@minValue(30)
@maxValue(730)
param retentionDays int = 30

@description('Daily Log Analytics ingestion limit in GB; data over the cap is not ingested.')
@minValue(1)
param dailyQuotaGb int = 1

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${name}-logs'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionDays
    workspaceCapping: {
      dailyQuotaGb: dailyQuotaGb
    }
    publicNetworkAccessForIngestion: 'Disabled'
    publicNetworkAccessForQuery: 'Disabled'
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${name}-insights'
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    DisableLocalAuth: true
    publicNetworkAccessForIngestion: 'Disabled'
    publicNetworkAccessForQuery: 'Disabled'
  }
}

output workspaceId string = workspace.id
output workspaceName string = workspace.name
output insightsId string = insights.id
