using '../main.bicep'

param environmentName = 'dev'
param resourceGroupName = 'rg-agent-blueprints-ors-foundry-e2e'
param location = 'eastus2'
param apiEntraClientId = '00000000-0000-0000-0000-000000000000'
param apiEntraAppIdUri = 'api://00000000-0000-0000-0000-000000000000'
param spaEntraClientId = '00000000-0000-0000-0000-000000000000'
param postgresAdministratorObjectId = '00000000-0000-0000-0000-000000000000'
param postgresAdministratorPrincipalName = 'deployment-operators'
param hostedWorkflowEndpoint = 'https://replace.invalid/responses'
param tags = {
  environment: 'dev'
  owner: 'replace-me'
  workload: 'agent-blueprints'
}
