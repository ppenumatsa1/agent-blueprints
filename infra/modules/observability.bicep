targetScope = 'resourceGroup'

param namePrefix string
param location string
param tags object
param retentionDays int
param dailyQuotaGb int

module workspace 'br/public:avm/res/operational-insights/workspace:0.16.2' = {
  name: 'log-analytics'
  params: {
    name: '${namePrefix}-law'
    location: location
    skuName: 'PerGB2018'
    dataRetention: retentionDays
    dailyQuotaGb: string(dailyQuotaGb)
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
    tags: tags
  }
}

module applicationInsights 'br/public:avm/res/insights/component:0.8.0' = {
  name: 'application-insights'
  params: {
    name: '${namePrefix}-appi'
    location: location
    applicationType: 'web'
    kind: 'web'
    workspaceResourceId: workspace.outputs.resourceId
    disableLocalAuth: true
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
    tags: tags
  }
}

output workspaceName string = workspace.outputs.name
output workspaceResourceId string = workspace.outputs.resourceId
output applicationInsightsName string = applicationInsights.outputs.name
output applicationInsightsResourceId string = applicationInsights.outputs.resourceId
@secure()
output applicationInsightsConnectionString string = applicationInsights.outputs.connectionString
