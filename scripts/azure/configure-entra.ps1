[CmdletBinding()]
param(
    [switch]$Apply,
    [ValidateSet('AzureCli', 'Azd')]
    [string]$DeploymentMode = 'AzureCli',
    [string]$SubscriptionId = $env:AZURE_SUBSCRIPTION_ID,
    [string]$TenantId = $env:AZURE_TENANT_ID,
    [string]$ExpectedUser = $env:AZURE_EXPECTED_USER,
    [string]$Location = $env:AZURE_LOCATION,
    [string]$ApiDisplayName = 'agent-blueprints-order-resolution-api',
    [string]$SpaDisplayName = 'agent-blueprints-order-resolution-spa',
    [string]$ApiAppIdUri,
    [string]$FrontendRedirectUri
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\common.ps1"

function Get-ExactApplication {
    param(
        [Parameter(Mandatory)]
        [string]$DisplayName
    )
    $raw = az ad app list --display-name $DisplayName --output json --only-show-errors
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to query Entra application $DisplayName."
    }
    $matches = @(
        $raw |
            ConvertFrom-Json |
            Where-Object { $_.displayName -ceq $DisplayName }
    )
    if ($matches.Count -gt 1) {
        throw "More than one Entra application uses display name $DisplayName."
    }
    return $matches | Select-Object -First 1
}

function Ensure-Application {
    param(
        [Parameter(Mandatory)]
        [string]$DisplayName
    )
    $application = Get-ExactApplication -DisplayName $DisplayName
    if (-not $application) {
        if (-not $Apply) {
            throw "Entra application $DisplayName is not configured."
        }
        az ad app create `
            --display-name $DisplayName `
            --sign-in-audience AzureADMyOrg `
            --output none `
            --only-show-errors
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to create Entra application $DisplayName."
        }
        $application = Get-ExactApplication -DisplayName $DisplayName
    }
    if ($application.signInAudience -cne 'AzureADMyOrg') {
        throw "Entra application $DisplayName must be single-tenant."
    }
    return $application
}

function Get-StableId {
    param(
        [AllowNull()]
        [object[]]$Items,
        [Parameter(Mandatory)]
        [string]$Value
    )
    $matches = @($Items | Where-Object { $_.value -ceq $Value })
    if ($matches.Count -gt 1) {
        throw "Duplicate Entra permission value: $Value"
    }
    if ($matches.Count -eq 1) {
        return [string]$matches[0].id
    }
    return [guid]::NewGuid().ToString()
}

function Invoke-GraphPatch {
    param(
        [Parameter(Mandatory)]
        [string]$ObjectId,
        [Parameter(Mandatory)]
        [hashtable]$Body
    )
    $json = $Body | ConvertTo-Json -Depth 12 -Compress
    az rest `
        --method patch `
        --url "https://graph.microsoft.com/v1.0/applications/$ObjectId" `
        --headers 'Content-Type=application/json' `
        --body $json `
        --output none `
        --only-show-errors
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to update Entra application object $ObjectId."
    }
}

function Set-AzdEnvironmentValue {
    param(
        [Parameter(Mandatory)]
        [string]$Name,
        [Parameter(Mandatory)]
        [string]$Value
    )
    $previousUserAgent = $env:AZURE_DEV_USER_AGENT
    try {
        $env:AZURE_DEV_USER_AGENT = 'microsoft_foundry_skill'
        azd env set $Name $Value --no-prompt | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to set azd environment value $Name."
        }
    }
    finally {
        $env:AZURE_DEV_USER_AGENT = $previousUserAgent
    }
}

function Assert-FrontendRedirectUri {
    param(
        [Parameter(Mandatory)]
        [string]$Value
    )
    $parsed = $null
    if (
        -not [uri]::TryCreate($Value, [System.UriKind]::Absolute, [ref]$parsed) -or
        $parsed.Scheme -cne 'https' -or
        $parsed.UserInfo -or
        $parsed.Query -or
        $parsed.Fragment -or
        $parsed.AbsolutePath -notin @('', '/')
    ) {
        throw 'FrontendRedirectUri must be one HTTPS origin without path, query, or fragment.'
    }
    return $parsed.GetLeftPart([System.UriPartial]::Authority)
}

if ($DeploymentMode -ceq 'Azd') {
    & "$PSScriptRoot\preflight.ps1" `
        -DeploymentMode Azd `
        -FromAzdEnvironment | Out-Null
    $values = Get-AzdEnvironmentValues
    $SubscriptionId = Get-RequiredValue $values 'AZURE_SUBSCRIPTION_ID'
    $TenantId = Get-RequiredValue $values 'AZURE_TENANT_ID'
} else {
    & "$PSScriptRoot\preflight.ps1" `
        -DeploymentMode AzureCli `
        -SubscriptionId $SubscriptionId `
        -TenantId $TenantId `
        -ExpectedUser $ExpectedUser `
        -Location $Location | Out-Null
}

$activeTenant = az account show --query tenantId --output tsv --only-show-errors
if ($LASTEXITCODE -ne 0 -or $activeTenant -cne $TenantId) {
    throw 'Azure CLI tenant does not match the selected deployment context.'
}

$apiApplication = Ensure-Application -DisplayName $ApiDisplayName
$spaApplication = Ensure-Application -DisplayName $SpaDisplayName
$resolvedApiAppIdUri = if ($ApiAppIdUri) { $ApiAppIdUri } else { "api://$($apiApplication.appId)" }
if ($resolvedApiAppIdUri -cne "api://$($apiApplication.appId)") {
    throw 'ApiAppIdUri must use the API application client ID.'
}

$redirectUris = @(
    'http://localhost:5173'
    'http://localhost:8080'
)
if ($FrontendRedirectUri) {
    $redirectUris += Assert-FrontendRedirectUri -Value $FrontendRedirectUri
}
$redirectUris = @($redirectUris | Sort-Object -Unique)

$existingScopes = @($apiApplication.api.oauth2PermissionScopes)
$scopeDefinitions = @(
    @{
        value = 'workflow.read'
        adminConsentDisplayName = 'Read workflow cases'
        adminConsentDescription = 'Read workflow cases available to the signed-in user.'
        userConsentDisplayName = 'Read workflow cases'
        userConsentDescription = 'Read workflow cases available to you.'
    }
    @{
        value = 'workflow.write'
        adminConsentDisplayName = 'Create workflow cases'
        adminConsentDescription = 'Create workflow cases for the signed-in user.'
        userConsentDisplayName = 'Create workflow cases'
        userConsentDescription = 'Create workflow cases for you.'
    }
    @{
        value = 'workflow.approve'
        adminConsentDisplayName = 'Decide assigned workflow cases'
        adminConsentDescription = 'Approve or reject workflow cases assigned to the signed-in user.'
        userConsentDisplayName = 'Decide assigned workflow cases'
        userConsentDescription = 'Approve or reject workflow cases assigned to you.'
    }
)
$scopes = @(
    foreach ($definition in $scopeDefinitions) {
        @{
            id = Get-StableId -Items $existingScopes -Value $definition.value
            isEnabled = $true
            type = 'User'
            value = $definition.value
            adminConsentDisplayName = $definition.adminConsentDisplayName
            adminConsentDescription = $definition.adminConsentDescription
            userConsentDisplayName = $definition.userConsentDisplayName
            userConsentDescription = $definition.userConsentDescription
        }
    }
)

$existingRoles = @($apiApplication.appRoles)
$roleDefinitions = @(
    @{
        value = 'Workflow.User'
        displayName = 'Workflow user'
        description = 'Submit and read workflow cases permitted by record authorization.'
    }
    @{
        value = 'Workflow.Approver'
        displayName = 'Workflow approver'
        description = 'Approve or reject assigned workflow cases.'
    }
)
$roles = @(
    foreach ($definition in $roleDefinitions) {
        @{
            id = Get-StableId -Items $existingRoles -Value $definition.value
            allowedMemberTypes = @('User')
            description = $definition.description
            displayName = $definition.displayName
            isEnabled = $true
            value = $definition.value
        }
    }
)

if ($Apply) {
    Invoke-GraphPatch -ObjectId $apiApplication.id -Body @{
        signInAudience = 'AzureADMyOrg'
        identifierUris = @($resolvedApiAppIdUri)
        appRoles = $roles
        api = @{
            requestedAccessTokenVersion = 2
            oauth2PermissionScopes = $scopes
            preAuthorizedApplications = @(
                @{
                    appId = $spaApplication.appId
                    delegatedPermissionIds = @($scopes.id)
                }
            )
        }
    }
    Invoke-GraphPatch -ObjectId $spaApplication.id -Body @{
        signInAudience = 'AzureADMyOrg'
        spa = @{
            redirectUris = $redirectUris
        }
        requiredResourceAccess = @(
            @{
                resourceAppId = $apiApplication.appId
                resourceAccess = @(
                    foreach ($scope in $scopes) {
                        @{
                            id = $scope.id
                            type = 'Scope'
                        }
                    }
                )
            }
        )
    }

    if ($DeploymentMode -ceq 'Azd') {
        Set-AzdEnvironmentValue -Name 'AZURE_API_ENTRA_CLIENT_ID' -Value $apiApplication.appId
        Set-AzdEnvironmentValue -Name 'AZURE_API_ENTRA_APP_ID_URI' -Value $resolvedApiAppIdUri
        Set-AzdEnvironmentValue -Name 'AZURE_SPA_ENTRA_CLIENT_ID' -Value $spaApplication.appId
    }
}

$apiApplication = Get-ExactApplication -DisplayName $ApiDisplayName
$spaApplication = Get-ExactApplication -DisplayName $SpaDisplayName
$configuredScopes = @($apiApplication.api.oauth2PermissionScopes)
$configuredRoles = @($apiApplication.appRoles)
$configuredPreauthorization = @(
    $apiApplication.api.preAuthorizedApplications |
        Where-Object { $_.appId -ceq $spaApplication.appId }
)
$configuredAccess = @(
    $spaApplication.requiredResourceAccess |
        Where-Object { $_.resourceAppId -ceq $apiApplication.appId }
)
$requiredScopeIds = @($scopes.id | Sort-Object)
$configuredScopeIds = @(
    $configuredPreauthorization.delegatedPermissionIds |
        Sort-Object
)
$configuredResourceScopeIds = @(
    $configuredAccess.resourceAccess |
        Where-Object { $_.type -ceq 'Scope' } |
        ForEach-Object { [string]$_.id } |
        Sort-Object
)

$valid = (
    $apiApplication.signInAudience -ceq 'AzureADMyOrg' -and
    $spaApplication.signInAudience -ceq 'AzureADMyOrg' -and
    $resolvedApiAppIdUri -in @($apiApplication.identifierUris) -and
    @($configuredScopes.value | Sort-Object) -join ',' -eq
        @($scopeDefinitions.value | Sort-Object) -join ',' -and
    @($configuredRoles.value | Sort-Object) -join ',' -eq
        @($roleDefinitions.value | Sort-Object) -join ',' -and
    @($redirectUris | Where-Object { $_ -notin @($spaApplication.spa.redirectUris) }).Count -eq 0 -and
    $requiredScopeIds -join ',' -eq $configuredScopeIds -join ',' -and
    $requiredScopeIds -join ',' -eq $configuredResourceScopeIds -join ','
)
if (-not $valid) {
    throw 'Entra application validation failed.'
}

[ordered]@{
    status = 'passed'
    mutationPerformed = [bool]$Apply
    tenantId = $TenantId
    apiClientId = $apiApplication.appId
    apiAppIdUri = $resolvedApiAppIdUri
    spaClientId = $spaApplication.appId
    redirectUris = $redirectUris
    delegatedScopes = @($scopeDefinitions.value)
    appRoles = @($roleDefinitions.value)
} | ConvertTo-Json -Depth 5
