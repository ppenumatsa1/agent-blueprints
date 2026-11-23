[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$SkipMigration,
    [ValidateSet('AzureCli', 'Azd')]
    [string]$DeploymentMode = 'AzureCli',
    [Parameter(Mandatory)]
    [string]$OperatorIp,
    [Parameter(Mandatory)]
    [string]$EnvironmentName,
    [string]$Location = 'eastus2',
    [string]$SubscriptionId = $env:AZURE_SUBSCRIPTION_ID,
    [string]$TenantId = $env:AZURE_TENANT_ID,
    [string]$ExpectedUser = $env:AZURE_EXPECTED_USER,
    [Parameter(Mandatory)]
    [string]$PostgresAdministratorObjectId,
    [Parameter(Mandatory)]
    [string]$PostgresAdministratorPrincipalName,
    [ValidateSet('Group', 'ServicePrincipal', 'User')]
    [string]$PostgresAdministratorPrincipalType = 'Group',
    [string]$OperatorObjectId,
    [switch]$EnableAcceptanceControls,
    [Parameter(Mandatory)]
    [string]$HostedWorkflowEndpoint,
    [Parameter(Mandatory)]
    [string]$HostedResponsesEndpoint,
    [Parameter(Mandatory)]
    [string]$HostedConversationEndpoint,
    [Parameter(Mandatory)]
    [string]$HostedAgentName,
    [Parameter(Mandatory)]
    [string]$HostedPublishOperationId,
    [Parameter(Mandatory)]
    [string]$HostedPublishJournal,
    [Parameter(Mandatory)]
    [string]$OutputsFile,
    [string]$WorkingRoot,
    [string]$ResourceGroupName = 'rg-agent-blueprints-ors-foundry-e2e',
    [string]$DeploymentName = 'agent-blueprints-foundry'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\common.ps1"

if (-not $Apply) {
    throw 'Deployment is disabled by default. Re-run with -Apply after validation and approval.'
}
if ($DeploymentMode -ceq 'Azd') {
    & "$PSScriptRoot\preflight.ps1" -DeploymentMode Azd -FromAzdEnvironment
    throw 'Azd mode is infrastructure-only and cannot deploy the generated hosted composition.'
}
if (-not $SubscriptionId -or -not $TenantId -or -not $ExpectedUser) {
    throw 'SubscriptionId, TenantId, and ExpectedUser are required in AzureCli mode.'
}
if ($HostedAgentName -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') {
    throw 'HostedAgentName must be one safe ARM path segment.'
}

foreach ($endpoint in @{
    HostedWorkflowEndpoint = @{
        Value = $HostedWorkflowEndpoint
        Suffix = "/agents/$HostedAgentName/endpoint/protocols/openai/responses"
    }
    HostedResponsesEndpoint = @{
        Value = $HostedResponsesEndpoint
        Suffix = "/agents/$HostedAgentName/endpoint/protocols/openai/responses"
    }
    HostedConversationEndpoint = @{
        Value = $HostedConversationEndpoint
        Suffix = "/agents/$HostedAgentName/endpoint/protocols/openai/conversations"
    }
}.GetEnumerator()) {
    $hostedUri = $null
    if (
        -not [uri]::TryCreate(
            $endpoint.Value.Value,
            [System.UriKind]::Absolute,
            [ref]$hostedUri
        ) -or
        $hostedUri.Scheme -cne 'https' -or
        $hostedUri.UserInfo -or
        $hostedUri.Fragment -or
        -not $hostedUri.AbsolutePath.TrimEnd('/').EndsWith(
            $endpoint.Value.Suffix,
            [System.StringComparison]::Ordinal
        ) -or
        $hostedUri.Query -cnotmatch '^\?api-version=[A-Za-z0-9._~-]+$'
    ) {
        throw "$($endpoint.Key) must be the selected agent's explicit Foundry HTTPS protocol endpoint with one api-version."
    }
}
if ($HostedWorkflowEndpoint -cne $HostedResponsesEndpoint) {
    throw 'HostedWorkflowEndpoint and HostedResponsesEndpoint must identify the same Responses endpoint.'
}
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
$sourceRevision = (git -C $root rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceRevision -cnotmatch '^[0-9a-f]{40}$') {
    throw 'Unable to resolve the exact source revision for deployment.'
}
$workingParent = if ($WorkingRoot) {
    [System.IO.Path]::GetFullPath($WorkingRoot)
}
else {
    Join-Path $root '.azure\deployment-work'
}
New-Item -ItemType Directory -Path $workingParent -Force | Out-Null
$temporaryRoot = Join-Path $workingParent (
    "agent-blueprints-order-resolution-{0}" -f [guid]::NewGuid().ToString('N')
)
$generatedRoot = Join-Path $temporaryRoot 'generated'
$parameterFile = Join-Path $temporaryRoot 'parameters.json'
$archivePath = Join-Path $temporaryRoot 'hosted-agent.zip'
$resolvedOutputsParent = Split-Path -Parent ([System.IO.Path]::GetFullPath($OutputsFile))
if (-not (Test-Path -LiteralPath $resolvedOutputsParent)) {
    New-Item -ItemType Directory -Path $resolvedOutputsParent -Force | Out-Null
}

New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
try {
    Push-Location $root
    try {
        python scripts\instantiate_maf.py --profile order-resolution $generatedRoot
        if ($LASTEXITCODE -ne 0) { throw 'Order Resolution generation failed.' }
    }
    finally {
        Pop-Location
    }
    $generatedRoot = Assert-GeneratedOrderResolutionProject -ProjectRoot $generatedRoot
    $generatedApiApp = Get-Content `
        -LiteralPath (Join-Path $generatedRoot 'backend\app\api\app.py') `
        -Raw
    $generatedApiConfig = Get-Content `
        -LiteralPath (Join-Path $generatedRoot 'backend\app\config.py') `
        -Raw
    $generatedHostedBridge = Get-Content `
        -LiteralPath (
            Join-Path $generatedRoot `
                'hosted-agent\src\order_resolution_hosted\bridge.py'
        ) `
        -Raw
    if (
        $generatedApiApp -notmatch [regex]::Escape('/api/internal/hosted/v1') -or
        $generatedApiConfig -notmatch '\bHOSTED_SERVICE_PRINCIPAL_ID\b' -or
        $generatedApiConfig -notmatch '\bHOSTED_SERVICE_APP_ROLE\b' -or
        $generatedHostedBridge -notmatch '\bdef\s+build_workflow_host\s*\('
    ) {
        throw 'Generated source does not expose the frozen hosted bridge and identity contract.'
    }
    $nginxPath = Join-Path $generatedRoot 'frontend\nginx.conf'
    $nginxSource = Get-Content -LiteralPath $nginxPath -Raw
    if ($nginxSource -notmatch [regex]::Escape('proxy_pass http://api:8000;')) {
        throw 'Generated frontend proxy contract changed; refusing to deploy an unverified upstream.'
    }
    $backendDockerfilePath = Join-Path $generatedRoot 'backend\Dockerfile'
    $backendDockerfile = Get-Content -LiteralPath $backendDockerfilePath -Raw
    if (
        $backendDockerfile -notmatch '\bca-certificates\b' -or
        $backendDockerfile -notmatch [regex]::Escape(
            'test -r /etc/ssl/certs/ca-certificates.crt'
        )
    ) {
        throw 'Generated backend image does not install and verify the system CA bundle.'
    }
    $generatedApiBuildContext = Assert-GeneratedApiImageContext `
        -ProjectRoot $generatedRoot

    & "$PSScriptRoot\preflight.ps1" `
        -DeploymentMode AzureCli `
        -SubscriptionId $SubscriptionId `
        -TenantId $TenantId `
        -ExpectedUser $ExpectedUser `
        -Location $Location `
        -OperatorObjectId $OperatorObjectId

    $entraJson = & "$PSScriptRoot\configure-entra.ps1" `
        -Apply `
        -DeploymentMode AzureCli `
        -SubscriptionId $SubscriptionId `
        -TenantId $TenantId `
        -ExpectedUser $ExpectedUser `
        -Location $Location
    $entra = $entraJson | ConvertFrom-Json

    $parameters = [ordered]@{
        '$schema' = 'https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#'
        contentVersion = '1.0.0.0'
        parameters = [ordered]@{
            environmentName = @{ value = $EnvironmentName }
            resourceGroupName = @{ value = $ResourceGroupName }
            location = @{ value = $Location }
            apiEntraClientId = @{ value = $entra.apiClientId }
            apiEntraAppIdUri = @{ value = $entra.apiAppIdUri }
            spaEntraClientId = @{ value = $entra.spaClientId }
            postgresAdministratorObjectId = @{ value = $PostgresAdministratorObjectId }
            postgresAdministratorPrincipalName = @{
                value = $PostgresAdministratorPrincipalName
            }
            postgresAdministratorPrincipalType = @{
                value = $PostgresAdministratorPrincipalType
            }
            hostedWorkflowEndpoint = @{ value = $HostedWorkflowEndpoint }
            agentVersion = @{ value = 'unpublished' }
            deploymentRevision = @{ value = $sourceRevision }
            acceptanceMode = @{ value = [bool]$EnableAcceptanceControls }
        }
    }
    $parameters | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $parameterFile

    & "$PSScriptRoot\what-if.ps1" `
        -Location $Location `
        -ParameterFile $parameterFile `
        -SubscriptionId $SubscriptionId `
        -TenantId $TenantId `
        -ExpectedUser $ExpectedUser `
        -DeploymentName "$DeploymentName-preview"

    Push-Location $root
    try {
        $deploymentJson = az deployment sub create `
            --subscription $SubscriptionId `
            --name $DeploymentName `
            --location $Location `
            --template-file infra\main.bicep `
            --parameters $parameterFile `
            --query properties.outputs `
            --output json `
            --only-show-errors
        if ($LASTEXITCODE -ne 0) { throw 'Subscription deployment failed.' }
    }
    finally {
        Pop-Location
    }

    $deploymentOutputs = $deploymentJson | ConvertFrom-Json -AsHashtable
    $values = @{}
    foreach ($name in $deploymentOutputs.Keys) {
        $values[$name.ToUpperInvariant()] = $deploymentOutputs[$name].value
    }
    $values['AZURE_SUBSCRIPTION_ID'] = $SubscriptionId
    $values['AZURE_TENANT_ID'] = $TenantId
    $values['AZURE_EXPECTED_USER'] = $ExpectedUser
    $values['AZURE_LOCATION'] = $Location
    $values['AZURE_ENV_NAME'] = $EnvironmentName
    $values['SOURCE_REVISION'] = $sourceRevision
    $values['DEPLOYMENT_REVISION'] = $sourceRevision
    $values['HOSTED_WORKFLOW_ENDPOINT'] = $HostedWorkflowEndpoint
    $values['AZURE_API_ENTRA_SERVICE_PRINCIPAL_ID'] =
        $entra.apiServicePrincipalObjectId
    $values['AZURE_HOSTED_API_APP_ROLE_ID'] = $entra.hostedServiceAppRoleId
    $values['AZURE_HOSTED_API_APP_ROLE_VALUE'] = $entra.hostedServiceRoleValue
    $values['AZURE_POSTGRES_ADMIN_PRINCIPAL_NAME'] =
        $PostgresAdministratorPrincipalName
    $hostedAgentScopeJson = python `
        "$PSScriptRoot\verify_hosted_agent_scope.py" `
        --project-id (Get-RequiredValue $values 'AZURE_AI_PROJECT_ID') `
        --agent-name $HostedAgentName
    if ($LASTEXITCODE -ne 0 -or -not $hostedAgentScopeJson) {
        throw 'Unable to derive the documented exact Foundry agent scope.'
    }
    $hostedAgentScope = $hostedAgentScopeJson | ConvertFrom-Json
    $values | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputsFile

    & "$PSScriptRoot\configure-entra.ps1" `
        -Apply `
        -DeploymentMode AzureCli `
        -SubscriptionId $SubscriptionId `
        -TenantId $TenantId `
        -ExpectedUser $ExpectedUser `
        -Location $Location `
        -FrontendRedirectUri "https://$(Get-RequiredValue $values 'AZURE_WEB_FQDN')" `
        -OperatorObjectId $OperatorObjectId | Out-Null

    & "$PSScriptRoot\configure-postgres.ps1" `
        -Apply `
        -DeploymentMode AzureCli `
        -ValuesFile $OutputsFile `
        -OperatorIp $OperatorIp
    $databaseUser = [uri]::EscapeDataString(
        (Get-RequiredValue $values 'AZURE_API_IDENTITY_NAME')
    )
    $databaseHost = Get-RequiredValue $values 'AZURE_POSTGRESQL_HOST'
    $databaseName = Get-RequiredValue $values 'AZURE_POSTGRESQL_DATABASE'
    $apiDatabaseUrl =
        "postgresql://${databaseUser}@${databaseHost}:5432/${databaseName}?sslmode=verify-full&sslrootcert=system"
    $migrationDatabaseUser = [uri]::EscapeDataString(
        $PostgresAdministratorPrincipalName
    )
    $migrationDatabaseUrl =
        "postgresql://${migrationDatabaseUser}@${databaseHost}:5432/${databaseName}?sslmode=verify-full&sslrootcert=system"
    if (-not $SkipMigration) {
        & "$PSScriptRoot\migrate.ps1" `
            -Apply `
            -DeploymentMode AzureCli `
            -ValuesFile $OutputsFile `
            -GeneratedProjectRoot $generatedRoot `
            -OperatorIp $OperatorIp
    }

    $acrName = Get-RequiredValue $values 'AZURE_CONTAINER_REGISTRY_NAME'
    $registryEndpoint = Get-RequiredValue $values 'AZURE_CONTAINER_REGISTRY_ENDPOINT'
    $imageTag = (git -C $root rev-parse --short=12 HEAD).Trim()
    Push-Location $generatedApiBuildContext
    try {
        az acr build `
            --subscription $SubscriptionId `
            --registry $acrName `
            --image "order-resolution-api:$imageTag" `
            --file Dockerfile `
            . `
            --only-show-errors
        if ($LASTEXITCODE -ne 0) { throw 'Generated API image build failed.' }
    }
    finally {
        Pop-Location
    }
    $apiDigest = az acr manifest show-metadata `
        --registry $acrName `
        --name "order-resolution-api:$imageTag" `
        --query digest `
        --output tsv `
        --only-show-errors
    if (-not $apiDigest) {
        throw 'Unable to resolve the generated API immutable image digest.'
    }
    $apiImage = "$registryEndpoint/order-resolution-api@$apiDigest"
    $resourceGroup = Get-RequiredValue $values 'AZURE_RESOURCE_GROUP'
    $apiName = Get-RequiredValue $values 'AZURE_API_CONTAINER_APP_NAME'
    $webName = Get-RequiredValue $values 'AZURE_WEB_CONTAINER_APP_NAME'
    $apiFqdn = Get-RequiredValue $values 'AZURE_API_FQDN'
    $apiEnvironment = @(
        'WORKFLOW_HOST=hosted',
        "DEPLOYMENT_REVISION=$sourceRevision",
        "ACCEPTANCE_MODE=$($EnableAcceptanceControls.ToString().ToLowerInvariant())",
        'HOSTED_WORKFLOW_SCOPE=https://ai.azure.com/.default',
        "API_MANAGED_IDENTITY_CLIENT_ID=$(Get-RequiredValue $values 'AZURE_API_IDENTITY_CLIENT_ID')",
        "DATABASE_URL=$apiDatabaseUrl",
        'DATABASE_AUTH_MODE=managed-identity',
        'DATABASE_TLS_MODE=verify-full',
        "DATABASE_MANAGED_IDENTITY_CLIENT_ID=$(Get-RequiredValue $values 'AZURE_API_IDENTITY_CLIENT_ID')",
        'PGSSLROOTCERT=system',
        "CORS_ORIGINS=https://$(Get-RequiredValue $values 'AZURE_WEB_FQDN')"
    )
    $bootstrapApiEnvironment = @(
        $apiEnvironment
        'AGENT_VERSION=unpublished'
        "HOSTED_WORKFLOW_ENDPOINT=$HostedWorkflowEndpoint"
        "HOSTED_CONVERSATION_ENDPOINT=$HostedConversationEndpoint"
        "HOSTED_SERVICE_PRINCIPAL_ID=$($entra.apiServicePrincipalObjectId)"
        'HOSTED_SERVICE_APP_ROLE=Hosted.Workflow.Invoke'
    )
    az containerapp update `
        --subscription $SubscriptionId `
        --resource-group $resourceGroup `
        --name $apiName `
        --image $apiImage `
        --set-env-vars $bootstrapApiEnvironment `
        --only-show-errors | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Generated API bootstrap deployment failed.' }
    try {
        $bootstrapHealth = Invoke-WebRequest `
            -Uri "https://$apiFqdn/healthz" `
            -Method Get `
            -TimeoutSec 30
    }
    catch {
        throw 'Generated API bootstrap health check failed.'
    }
    if ($bootstrapHealth.StatusCode -notin @(200, 204)) {
        throw "Generated API bootstrap health returned $($bootstrapHealth.StatusCode)."
    }

    $orderResolutionApiEndpoint = "https://$apiFqdn/api/internal/hosted/v1"
    $orderResolutionApiScope = "$($entra.apiAppIdUri)/.default"
    $applicationInsightsResourceId =
        Get-RequiredValue $values 'APPLICATIONINSIGHTS_RESOURCE_ID'
    $applicationInsightsConnectionString = az resource show `
        --subscription $SubscriptionId `
        --ids $applicationInsightsResourceId `
        --api-version 2020-02-02 `
        --query properties.ConnectionString `
        --output tsv `
        --only-show-errors
    if ($LASTEXITCODE -ne 0 -or -not $applicationInsightsConnectionString) {
        throw 'Application Insights connection resolution failed.'
    }
    $publisher = Join-Path $generatedRoot 'scripts\foundry\publish_order_resolution_hosted.py'
    $hostedRequirements = Join-Path $generatedRoot 'hosted-agent\requirements.txt'
    function Invoke-HostedPublisher {
        param([switch]$RequireActive)
        $arguments = @(
            $publisher,
            $generatedRoot,
            '--archive',
            $archivePath,
            '--publish',
            '--agent-name',
            $HostedAgentName,
            '--operation-id',
            $HostedPublishOperationId,
            '--journal',
            $HostedPublishJournal
        )
        if ($RequireActive) {
            $arguments += '--require-active'
        }
        $output = & uv run `
            --with-requirements $hostedRequirements `
            python @arguments
        if ($LASTEXITCODE -ne 0) {
            throw 'Hosted Agent publish failed or became ambiguous; do not replay automatically.'
        }
        return $output[-1] | ConvertFrom-Json
    }

    function Assert-HostedPublishRecord {
        param(
            [Parameter(Mandatory)]
            [object]$Record,
            [switch]$RequireActive,
            [object]$ExpectedIdentity
        )
        if (
            $Record.status -cne 'acknowledged' -or
            $Record.provisioning_status -cnotin @('creating', 'active') -or
            -not $Record.agent_version -or
            -not $Record.identity_principal_id -or
            -not $Record.identity_client_id -or
            -not $Record.agent_version_id -or
            -not $Record.agent_guid
        ) {
            throw 'Hosted Agent publisher did not return an acknowledged version identity.'
        }
        if ($RequireActive -and $Record.provisioning_status -cne 'active') {
            throw 'Hosted Agent publisher did not confirm an active version.'
        }
        if ($ExpectedIdentity) {
            foreach ($field in @(
                'agent_version',
                'agent_version_id',
                'agent_guid',
                'identity_principal_id',
                'identity_client_id'
            )) {
                if ($Record.$field -cne $ExpectedIdentity.$field) {
                    throw "Hosted Agent identity changed between publication stages: $field"
                }
            }
        }
        return $Record
    }

    $publisherEnvironmentNames = @(
        'FOUNDRY_PROJECT_ENDPOINT'
        'FOUNDRY_PROJECT_ID'
        'AZURE_AI_MODEL_DEPLOYMENT_NAME'
        'ORDER_RESOLUTION_API_ENDPOINT'
        'ORDER_RESOLUTION_API_SCOPE'
        'ORDER_RESOLUTION_API_TIMEOUT_SECONDS'
        'APPLICATIONINSIGHTS_CONNECTION_STRING'
        'DATABASE_URL'
        'PGSSLROOTCERT'
        'ORDER_RESOLUTION_HOSTED_IDENTITY_BINDINGS'
        'ORDER_RESOLUTION_OPERATION_JOURNAL'
        @(
            Get-ChildItem Env: |
                Where-Object { $_.Name.StartsWith('DATABASE_') } |
                ForEach-Object Name
        )
    ) | Sort-Object -Unique
    $previousPublisherEnvironment = @{}
    foreach ($name in $publisherEnvironmentNames) {
        $previousPublisherEnvironment[$name] = [Environment]::GetEnvironmentVariable($name)
        Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
    }
    $publishRecord = $null
    $agentAssignment = $null
    try {
        $env:FOUNDRY_PROJECT_ENDPOINT = Get-RequiredValue $values 'AZURE_AI_PROJECT_ENDPOINT'
        $env:FOUNDRY_PROJECT_ID = Get-RequiredValue $values 'AZURE_AI_PROJECT_ID'
        $env:AZURE_AI_MODEL_DEPLOYMENT_NAME =
            Get-RequiredValue $values 'AZURE_AI_MODEL_DEPLOYMENT_NAME'
        $env:ORDER_RESOLUTION_API_ENDPOINT = $orderResolutionApiEndpoint
        $env:ORDER_RESOLUTION_API_SCOPE = $orderResolutionApiScope
        $env:ORDER_RESOLUTION_API_TIMEOUT_SECONDS = '30'
        $env:APPLICATIONINSIGHTS_CONNECTION_STRING =
            $applicationInsightsConnectionString
        $pendingPublishRecord = Assert-HostedPublishRecord `
            -Record (Invoke-HostedPublisher)

        $agentAssignmentJson = az role assignment create `
            --subscription $SubscriptionId `
            --assignee-object-id (Get-RequiredValue $values 'AZURE_API_IDENTITY_PRINCIPAL_ID') `
            --assignee-principal-type ServicePrincipal `
            --role 'eed3b665-ab3a-47b6-8f48-c9382fb1dad6' `
            --scope $hostedAgentScope.scope `
            --output json `
            --only-show-errors
        if ($LASTEXITCODE -ne 0) {
            throw 'Unable to grant Agent Consumer at the hosted agent scope.'
        }
        $agentAssignment = $agentAssignmentJson | ConvertFrom-Json

        $hostedEntraJson = & "$PSScriptRoot\configure-entra.ps1" `
            -Apply `
            -DeploymentMode AzureCli `
            -SubscriptionId $SubscriptionId `
            -TenantId $TenantId `
            -ExpectedUser $ExpectedUser `
            -Location $Location `
            -FrontendRedirectUri "https://$(Get-RequiredValue $values 'AZURE_WEB_FQDN')" `
            -OperatorObjectId $OperatorObjectId `
            -HostedServicePrincipalObjectId $pendingPublishRecord.identity_principal_id
        $hostedEntra = $hostedEntraJson | ConvertFrom-Json

        $publishRecord = Assert-HostedPublishRecord `
            -Record (Invoke-HostedPublisher -RequireActive) `
            -RequireActive `
            -ExpectedIdentity $pendingPublishRecord

        $allowedApplications = @(
            $entra.spaClientId
            $publishRecord.identity_client_id
        )
        if ($EnableAcceptanceControls) {
            $allowedApplications += '04b07795-8ddb-461a-bbee-02f9e1bf7b46'
        }
        $authClientArguments = @(
            "$PSScriptRoot\configure-container-app-auth-clients.py"
            '--subscription'
            $SubscriptionId
            '--resource-group'
            $resourceGroup
            '--app-name'
            $apiName
        )
        foreach ($clientId in $allowedApplications) {
            $authClientArguments += @('--allowed-application', $clientId)
        }
        python @authClientArguments | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'Unable to configure the API authentication client allowlist.'
        }
    }
    finally {
        foreach ($name in $previousPublisherEnvironment.Keys) {
            if ($null -eq $previousPublisherEnvironment[$name]) {
                Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
            } else {
                Set-Item -Path "Env:$name" -Value $previousPublisherEnvironment[$name]
            }
        }
    }

    az containerapp update `
        --subscription $SubscriptionId `
        --resource-group $resourceGroup `
        --name $apiName `
        --image $apiImage `
        --set-env-vars @(
            $apiEnvironment
            "AGENT_VERSION=$($publishRecord.agent_version)"
            "HOSTED_WORKFLOW_ENDPOINT=$HostedWorkflowEndpoint"
            "HOSTED_CONVERSATION_ENDPOINT=$HostedConversationEndpoint"
            "HOSTED_SERVICE_PRINCIPAL_ID=$($publishRecord.identity_principal_id)"
            "HOSTED_SERVICE_APP_ROLE=$($hostedEntra.hostedServiceRoleValue)"
        ) `
        --only-show-errors | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Generated API final deployment failed.' }

    $patchedNginx = $nginxSource.Replace(
        'proxy_pass http://api:8000;',
        "proxy_ssl_server_name on;`n        proxy_pass https://$apiFqdn;"
    )
    Set-Content -LiteralPath $nginxPath -Value $patchedNginx -NoNewline
    Push-Location (Join-Path $generatedRoot 'frontend')
    try {
        az acr build `
            --subscription $SubscriptionId `
            --registry $acrName `
            --image "order-resolution-web:$imageTag" `
            --file Dockerfile `
            --build-arg "VITE_ENTRA_TENANT_ID=$TenantId" `
            --build-arg "VITE_ENTRA_SPA_CLIENT_ID=$($entra.spaClientId)" `
            --build-arg "VITE_ENTRA_API_APP_ID_URI=$($entra.apiAppIdUri)" `
            . `
            --only-show-errors
        if ($LASTEXITCODE -ne 0) { throw 'Generated frontend image build failed.' }
    }
    finally {
        Pop-Location
    }

    $webDigest = az acr manifest show-metadata `
        --registry $acrName `
        --name "order-resolution-web:$imageTag" `
        --query digest `
        --output tsv `
        --only-show-errors
    if (-not $webDigest) {
        throw 'Unable to resolve the generated frontend immutable image digest.'
    }
    $webImage = "$registryEndpoint/order-resolution-web@$webDigest"
    az containerapp update `
        --subscription $SubscriptionId `
        --resource-group $resourceGroup `
        --name $webName `
        --image $webImage `
        --only-show-errors | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Generated frontend deployment failed.' }

    $values['AZURE_API_IMAGE'] = $apiImage
    $values['AZURE_WEB_IMAGE'] = $webImage
    $values['AZURE_HOSTED_AGENT_NAME'] = $HostedAgentName
    $values['AZURE_HOSTED_AGENT_VERSION'] = $publishRecord.agent_version
    $values['AGENT_VERSION'] = $publishRecord.agent_version
    $values['ACCEPTANCE_MODE'] =
        $EnableAcceptanceControls.ToString().ToLowerInvariant()
    $values['AZURE_HOSTED_AGENT_VERSION_ID'] = $publishRecord.agent_version_id
    $values['AZURE_HOSTED_AGENT_GUID'] = $publishRecord.agent_guid
    $values['AZURE_HOSTED_AGENT_PRINCIPAL_ID'] = $publishRecord.identity_principal_id
    $values['AZURE_HOSTED_AGENT_CLIENT_ID'] = $publishRecord.identity_client_id
    $values['AZURE_HOSTED_AGENT_PROVISIONING_STATUS'] =
        $publishRecord.provisioning_status
    $values['AZURE_HOSTED_AGENT_RBAC_SCOPE'] = $hostedAgentScope.scope
    $values['AZURE_HOSTED_AGENT_RBAC_SCOPE_SOURCE'] = $hostedAgentScope.source
    $values['AZURE_API_HOSTED_AGENT_ROLE_ASSIGNMENT_ID'] = $agentAssignment.id
    $values['AZURE_HOSTED_API_APP_ROLE_ASSIGNMENT_ID'] =
        $hostedEntra.hostedServiceAssignmentId
    $values['AZURE_HOSTED_API_APP_ROLE_ID'] = $hostedEntra.hostedServiceAppRoleId
    $values['AZURE_HOSTED_API_APP_ROLE_VALUE'] = $hostedEntra.hostedServiceRoleValue
    $values['AZURE_ACCEPTANCE_OPERATOR_OBJECT_ID'] = $OperatorObjectId
    $values['AZURE_ACCEPTANCE_OPERATOR_ASSIGNMENTS'] = @($hostedEntra.operatorAssignments)
    $values['ORDER_RESOLUTION_API_ENDPOINT'] = $orderResolutionApiEndpoint
    $values['ORDER_RESOLUTION_API_SCOPE'] = $orderResolutionApiScope
    $values['HOSTED_WORKFLOW_ENDPOINT'] = $HostedWorkflowEndpoint
    $values['AZURE_HOSTED_AGENT_RESPONSES_ENDPOINT'] = $HostedResponsesEndpoint
    $values['AZURE_HOSTED_AGENT_CONVERSATION_ENDPOINT'] = $HostedConversationEndpoint
    $values['AZURE_HOSTED_AGENT_ADAPTER_ENDPOINT'] = $HostedWorkflowEndpoint
    $values['AZURE_API_URL'] = "https://$apiFqdn"
    $values['AZURE_WEB_URL'] =
        "https://$(Get-RequiredValue $values 'AZURE_WEB_FQDN')"
    $values['AZURE_API_DATABASE_URL'] = $apiDatabaseUrl
    $values['AZURE_API_DATABASE_USER'] =
        Get-RequiredValue $values 'AZURE_API_IDENTITY_NAME'
    $values['MIGRATION_DATABASE_URL'] = $migrationDatabaseUrl
    $values['MIGRATION_DATABASE_USER'] = $PostgresAdministratorPrincipalName
    $values['MIGRATION_DATABASE_PASSWORD_REFERENCE'] =
        'transient-ref:azure-postgresql-access-token'
    $values['DATABASE_POOL_MIN_SIZE'] = '0'
    $values['DATABASE_POOL_MAX_SIZE'] = '8'
    $values['DATABASE_POOL_TIMEOUT_SECONDS'] = '30'
    $values['DATABASE_CONNECTION_MAX_LIFETIME_SECONDS'] = '900'
    $values['CORS_ORIGINS'] = "https://$(Get-RequiredValue $values 'AZURE_WEB_FQDN')"
    $values['APPLICATIONINSIGHTS_CONNECTION_STRING_REFERENCE'] =
        'secretref:applicationinsights-connection-string'
    $values['AZURE_API_REVISION'] = az containerapp show `
        --subscription $SubscriptionId `
        --resource-group $resourceGroup `
        --name $apiName `
        --query properties.latestReadyRevisionName `
        --output tsv
    $values['AZURE_WEB_REVISION'] = az containerapp show `
        --subscription $SubscriptionId `
        --resource-group $resourceGroup `
        --name $webName `
        --query properties.latestReadyRevisionName `
        --output tsv
    $values | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputsFile

    python "$PSScriptRoot\health-check.py" `
        --deployment-mode azure-cli `
        --values-file $OutputsFile
    if ($LASTEXITCODE -ne 0) { throw 'Deployment health verification failed.' }
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
