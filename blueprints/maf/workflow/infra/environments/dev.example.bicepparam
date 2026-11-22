using '../main.bicep'

param environmentName = 'example-dev'
param location = 'example-region'
param postgresAdministratorObjectId = '00000000-0000-4000-8000-000000000001'
param postgresAdministratorPrincipalName = 'example-admin-group'
param apiEntraClientId = '00000000-0000-4000-8000-000000000002'
param grantProjectAgentConsumer = false
param deployModel = false
param createRegistry = false
param createContainerApps = false
