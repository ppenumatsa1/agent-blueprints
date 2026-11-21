using '../main.bicep'

param environmentName = 'example-prod'
param location = 'example-region'
param postgresAdministratorObjectId = '00000000-0000-4000-8000-000000000001'
param postgresAdministratorPrincipalName = 'example-admin-group'
param apiEntraClientId = '00000000-0000-4000-8000-000000000002'
param deployModel = false
param createRegistry = false
param createContainerApps = false
