targetScope = 'resourceGroup'

param namePrefix string
param location string
param tags object
param workspaceName string
param apiIdentityId string
param apiIdentityClientId string
param apiIdentityName string
param webIdentityId string
param apiEntraClientId string
param apiEntraAppIdUri string
param registryServer string
param keyVaultName string
param apiSecretReferences array

@secure()
param applicationInsightsConnectionString string

param foundryProjectEndpoint string
param modelDeploymentName string
param postgresHost string
param postgresDatabaseName string
param hostedWorkflowEndpoint string
param agentVersion string
param deploymentRevision string
param acceptanceMode bool
param minReplicas int
param maxReplicas int

param apiImage string
param webImage string

var secretEnvironment = [
  for secret in apiSecretReferences: {
    name: secret.environmentName
    secretRef: secret.name
  }
]
var keyVaultUri = 'https://${keyVaultName}${az.environment().suffixes.keyvaultDns}/'
var keyVaultSecrets = [
  for secret in apiSecretReferences: {
    identity: apiIdentityId
    keyVaultUrl: '${keyVaultUri}secrets/${secret.keyVaultSecretName}'
    name: secret.name
  }
]
var apiSecrets = concat([
  {
    name: 'applicationinsights-connection-string'
    value: applicationInsightsConnectionString
  }
], keyVaultSecrets)

resource workspace 'Microsoft.OperationalInsights/workspaces@2025-07-01' existing = {
  name: workspaceName
}

resource environment 'Microsoft.App/managedEnvironments@2025-07-01' = {
  name: '${namePrefix}-cae'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    publicNetworkAccess: 'Enabled'
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    zoneRedundant: false
  }
}

resource api 'Microsoft.App/containerApps@2025-07-01' = {
  name: '${namePrefix}-api'
  location: location
  tags: union(tags, {
    'azd-service-name': 'api'
  })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${apiIdentityId}': {}
    }
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        allowInsecure: false
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          identity: apiIdentityId
          server: registryServer
        }
      ]
      secrets: apiSecrets
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          env: concat([
            {
              name: 'APPLICATIONINSIGHTS_AUTHENTICATION_STRING'
              value: 'Authorization=AAD;ClientId=${apiIdentityClientId}'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              secretRef: 'applicationinsights-connection-string'
            }
            {
              name: 'AGENT_VERSION'
              value: agentVersion
            }
            {
              name: 'ACCEPTANCE_MODE'
              value: string(acceptanceMode)
            }
            {
              name: 'AZURE_AI_MODEL_DEPLOYMENT_NAME'
              value: modelDeploymentName
            }
            {
              name: 'AZURE_AI_PROJECT_ENDPOINT'
              value: foundryProjectEndpoint
            }
            {
              name: 'AZURE_CLIENT_ID'
              value: apiIdentityClientId
            }
            {
              name: 'API_MANAGED_IDENTITY_CLIENT_ID'
              value: apiIdentityClientId
            }
            {
              name: 'CORS_ORIGINS'
              value: 'https://${web.properties.configuration.ingress.fqdn}'
            }
            {
              name: 'DATABASE_URL'
              value: 'postgresql://${uriComponent(apiIdentityName)}@${postgresHost}:5432/${postgresDatabaseName}?sslmode=verify-full&sslrootcert=system'
            }
            {
              name: 'DATABASE_AUTH_MODE'
              value: 'managed-identity'
            }
            {
              name: 'DATABASE_CONNECTION_MAX_LIFETIME_SECONDS'
              value: '900'
            }
            {
              name: 'DATABASE_MANAGED_IDENTITY_CLIENT_ID'
              value: apiIdentityClientId
            }
            {
              name: 'DATABASE_POOL_MAX_SIZE'
              value: '8'
            }
            {
              name: 'DATABASE_POOL_MIN_SIZE'
              value: '0'
            }
            {
              name: 'DATABASE_POOL_TIMEOUT_SECONDS'
              value: '30'
            }
            {
              name: 'DATABASE_TLS_MODE'
              value: 'verify-full'
            }
            {
              name: 'DEPLOYMENT_REVISION'
              value: deploymentRevision
            }
            {
              name: 'AZURE_POSTGRESQL_DATABASE'
              value: postgresDatabaseName
            }
            {
              name: 'AZURE_POSTGRESQL_HOST'
              value: postgresHost
            }
            {
              name: 'DB_SCHEMA_MANAGED_EXTERNALLY'
              value: 'true'
            }
            {
              name: 'ENTRA_API_CLIENT_ID'
              value: apiEntraClientId
            }
            {
              name: 'ENTRA_TENANT_ID'
              value: tenant().tenantId
            }
            {
              name: 'HOSTED_WORKFLOW_ENDPOINT'
              value: hostedWorkflowEndpoint
            }
            {
              name: 'HOSTED_WORKFLOW_SCOPE'
              value: 'https://ai.azure.com/.default'
            }
            {
              name: 'OBO_ENABLED'
              value: 'false'
            }
            {
              name: 'PGSSLROOTCERT'
              value: 'system'
            }
            {
              name: 'TELEMETRY_MODE'
              value: 'azure-monitor'
            }
            {
              name: 'WORKFLOW_HOST'
              value: 'hosted'
            }
          ], secretEnvironment)
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
      scale: {
        maxReplicas: maxReplicas
        minReplicas: minReplicas
      }
    }
  }
}

resource apiAuthentication 'Microsoft.App/containerApps/authConfigs@2025-07-01' = {
  parent: api
  name: 'current'
  properties: {
    globalValidation: {
      excludedPaths: [
        '/healthz'
      ]
      unauthenticatedClientAction: 'Return401'
    }
    httpSettings: {
      requireHttps: true
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: apiEntraClientId
          openIdIssuer: '${az.environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'
        }
        validation: {
          allowedAudiences: [
            apiEntraClientId
            apiEntraAppIdUri
          ]
        }
      }
    }
    login: {
      tokenStore: {
        enabled: false
      }
    }
    platform: {
      enabled: true
    }
  }
}

resource web 'Microsoft.App/containerApps@2025-07-01' = {
  name: '${namePrefix}-web'
  location: location
  tags: union(tags, {
    'azd-service-name': 'web'
  })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${webIdentityId}': {}
    }
  }
  properties: {
    environmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        allowInsecure: false
        external: true
        targetPort: 8080
        transport: 'auto'
      }
      registries: [
        {
          identity: webIdentityId
          server: registryServer
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: webImage
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        maxReplicas: maxReplicas
        minReplicas: minReplicas
      }
    }
  }
}

output environmentName string = environment.name
output environmentId string = environment.id
output apiName string = api.name
output apiFqdn string = api.properties.configuration.ingress.fqdn
output webName string = web.name
output webFqdn string = web.properties.configuration.ingress.fqdn
