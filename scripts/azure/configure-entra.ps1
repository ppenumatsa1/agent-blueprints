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
    [string]$FrontendRedirectUri,
    [string]$HostedServicePrincipalObjectId,
    [string]$OperatorObjectId,
    [string[]]$OperatorClientApplicationIds = @(
        '04b07795-8ddb-461a-bbee-02f9e1bf7b46'
    )
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

function Invoke-GraphJson {
    param(
        [Parameter(Mandatory)]
        [ValidateSet('patch', 'post')]
        [string]$Method,
        [Parameter(Mandatory)]
        [string]$Url,
        [Parameter(Mandatory)]
        [hashtable]$Body,
        [Parameter(Mandatory)]
        [int]$Depth,
        [ValidateSet('json', 'none')]
        [string]$Output = 'none'
    )
    $bodyPath = Join-Path ([System.IO.Path]::GetTempPath()) (
        "agent-blueprints-graph-{0}.json" -f [guid]::NewGuid().ToString('N')
    )
    try {
        $Body |
            ConvertTo-Json -Depth $Depth -Compress |
            Set-Content -LiteralPath $bodyPath -Encoding utf8NoBOM
        $bodyArgument = "@$bodyPath"
        $result = az rest `
            --method $Method `
            --url $Url `
            --headers 'Content-Type=application/json' `
            --body $bodyArgument `
            --output $Output `
            --only-show-errors
        if ($LASTEXITCODE -ne 0) {
            throw "Microsoft Graph $Method failed for $Url."
        }
        return $result
    }
    finally {
        Remove-Item -LiteralPath $bodyPath -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-GraphPatch {
    param(
        [Parameter(Mandatory)]
        [string]$ObjectId,
        [Parameter(Mandatory)]
        [hashtable]$Body
    )
    try {
        Invoke-GraphJson `
            -Method patch `
            -Url "https://graph.microsoft.com/v1.0/applications/$ObjectId" `
            -Body $Body `
            -Depth 12
    }
    catch {
        throw "Unable to update Entra application object $ObjectId."
    }
}

function Invoke-GraphPost {
    param(
        [Parameter(Mandatory)]
        [string]$Url,
        [Parameter(Mandatory)]
        [hashtable]$Body
    )
    try {
        $result = Invoke-GraphJson `
            -Method post `
            -Url $Url `
            -Body $Body `
            -Depth 8 `
            -Output json
    }
    catch {
        throw "Unable to create Microsoft Graph resource at $Url."
    }
    return $result | ConvertFrom-Json
}

function Ensure-ServicePrincipal {
    param(
        [Parameter(Mandatory)]
        [string]$ApplicationId
    )
    $raw = az ad sp show --id $ApplicationId --output json --only-show-errors 2>$null
    if ($LASTEXITCODE -ne 0) {
        if (-not $Apply) {
            throw "Service principal for application $ApplicationId is not configured."
        }
        az ad sp create --id $ApplicationId --output none --only-show-errors
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to create service principal for application $ApplicationId."
        }
        $raw = az ad sp show --id $ApplicationId --output json --only-show-errors
    }
    return $raw | ConvertFrom-Json
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
$operatorClientIds = @(
    $OperatorClientApplicationIds |
        ForEach-Object {
            $clientId = [guid]::Empty
            if (-not [guid]::TryParse($_, [ref]$clientId)) {
                throw 'OperatorClientApplicationIds must contain Entra application GUIDs.'
            }
            $clientId.ToString()
        } |
        Sort-Object -Unique
)
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
        allowedMemberTypes = @('User')
    }
    @{
        value = 'Workflow.Approver'
        displayName = 'Workflow approver'
        description = 'Approve or reject assigned workflow cases.'
        allowedMemberTypes = @('User')
    }
    @{
        value = 'Acceptance.Operator'
        displayName = 'Acceptance operator'
        description = 'Run bounded synthetic acceptance controls in an explicitly enabled environment.'
        allowedMemberTypes = @('User')
    }
    @{
        value = 'Hosted.Workflow.Invoke'
        displayName = 'Hosted workflow service'
        description = 'Use internal hosted-workflow business-state operations.'
        allowedMemberTypes = @('Application')
    }
)
$roles = @(
    foreach ($definition in $roleDefinitions) {
        @{
            id = Get-StableId -Items $existingRoles -Value $definition.value
            allowedMemberTypes = $definition.allowedMemberTypes
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
            preAuthorizedApplications = @()
        }
    }
    $scopeIds = @($scopes.id | Sort-Object)
    $publishedScopeIds = @()
    foreach ($attempt in 1..10) {
        $apiApplication = Get-ExactApplication -DisplayName $ApiDisplayName
        $publishedScopeIds = @(
            $apiApplication.api.oauth2PermissionScopes.id | Sort-Object
        )
        if (
            $publishedScopeIds.Count -eq $scopeIds.Count -and
            -not (Compare-Object $scopeIds $publishedScopeIds)
        ) {
            break
        }
        Start-Sleep -Seconds 1
    }
    if (
        $publishedScopeIds.Count -ne $scopeIds.Count -or
        (Compare-Object $scopeIds $publishedScopeIds)
    ) {
        throw 'Microsoft Graph did not publish the configured delegated scopes.'
    }
    Invoke-GraphPatch -ObjectId $apiApplication.id -Body @{
        signInAudience = 'AzureADMyOrg'
        identifierUris = @($resolvedApiAppIdUri)
        appRoles = $roles
        api = @{
            requestedAccessTokenVersion = 2
            oauth2PermissionScopes = $scopes
            preAuthorizedApplications = @(
                foreach ($clientId in @($spaApplication.appId) + $operatorClientIds) {
                    @{
                        appId = $clientId
                        delegatedPermissionIds = $scopeIds
                    }
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
$apiServicePrincipal = Ensure-ServicePrincipal -ApplicationId $apiApplication.appId
$configuredScopes = @($apiApplication.api.oauth2PermissionScopes)
$configuredRoles = @($apiApplication.appRoles)
$configuredHostedServiceRoles = @(
    $configuredRoles |
        Where-Object {
            $_.value -ceq 'Hosted.Workflow.Invoke' -and
            @($_.allowedMemberTypes).Count -eq 1 -and
            $_.allowedMemberTypes[0] -ceq 'Application'
        }
)
$configuredPreauthorization = @(
    $apiApplication.api.preAuthorizedApplications |
        Where-Object {
            $_.appId -cin (@($spaApplication.appId) + $operatorClientIds)
        }
)
$configuredAccess = @(
    $spaApplication.requiredResourceAccess |
        Where-Object { $_.resourceAppId -ceq $apiApplication.appId }
)
$requiredScopeIds = @($scopes.id | Sort-Object)
$configuredClientIds = @($configuredPreauthorization.appId | Sort-Object)
$requiredClientIds = @(
    (@($spaApplication.appId) + $operatorClientIds) | Sort-Object -Unique
)
$configuredClientsHaveScopes = @(
    $configuredPreauthorization |
        Where-Object {
            [bool](Compare-Object `
                $requiredScopeIds `
                @($_.delegatedPermissionIds | Sort-Object))
        }
).Count -eq 0
$configuredResourceScopeIds = @(
    $configuredAccess.resourceAccess |
        Where-Object { $_.type -ceq 'Scope' } |
        ForEach-Object { [string]$_.id } |
        Sort-Object
)
$configuredScopeValues = @($configuredScopes.value | Sort-Object)
$requiredScopeValues = @($scopeDefinitions.value | Sort-Object)
$configuredRoleValues = @($configuredRoles.value | Sort-Object)
$requiredRoleValues = @($roleDefinitions.value | Sort-Object)

$valid = (
    $apiApplication.signInAudience -ceq 'AzureADMyOrg' -and
    $spaApplication.signInAudience -ceq 'AzureADMyOrg' -and
    $resolvedApiAppIdUri -in @($apiApplication.identifierUris) -and
        -not (Compare-Object $requiredScopeValues $configuredScopeValues) -and
        -not (Compare-Object $requiredRoleValues $configuredRoleValues) -and
    $configuredHostedServiceRoles.Count -eq 1 -and
    @($redirectUris | Where-Object { $_ -notin @($spaApplication.spa.redirectUris) }).Count -eq 0 -and
        -not (Compare-Object $requiredClientIds $configuredClientIds) -and
    $configuredClientsHaveScopes -and
        -not (Compare-Object $requiredScopeIds $configuredResourceScopeIds)
)
if (-not $valid) {
    throw 'Entra application validation failed.'
}

$hostedServiceRole = $configuredRoles |
    Where-Object { $_.value -ceq 'Hosted.Workflow.Invoke' } |
    Select-Object -First 1
$apiAssignmentUrl =
    "https://graph.microsoft.com/v1.0/servicePrincipals/$($apiServicePrincipal.id)/appRoleAssignments"
$apiAssignmentPayload = az rest `
    --method get `
    --url $apiAssignmentUrl `
    --output json `
    --only-show-errors
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to inspect API service-principal app-role assignments.'
}
$apiSelfAssignments = @(
    ($apiAssignmentPayload | ConvertFrom-Json).value |
        Where-Object {
            $_.resourceId -ceq $apiServicePrincipal.id -and
            $_.appRoleId -ceq $hostedServiceRole.id
        }
)
if ($apiSelfAssignments.Count -ne 0) {
    throw 'The API bootstrap service principal must not hold the hosted-service role.'
}
$hostedServiceAssignment = $null
if ($HostedServicePrincipalObjectId) {
    $hostedPrincipalGuid = [guid]::Empty
    if (-not [guid]::TryParse($HostedServicePrincipalObjectId, [ref]$hostedPrincipalGuid)) {
        throw 'HostedServicePrincipalObjectId must be one Entra object GUID.'
    }
    $assignmentUrl =
        "https://graph.microsoft.com/v1.0/servicePrincipals/$HostedServicePrincipalObjectId/appRoleAssignments"
    $assignmentPayload = az rest `
        --method get `
        --url $assignmentUrl `
        --output json `
        --only-show-errors
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to inspect hosted-service API app-role assignments.'
    }
    $hostedServiceAssignments = @(
        ($assignmentPayload | ConvertFrom-Json).value |
            Where-Object {
                $_.resourceId -ceq $apiServicePrincipal.id -and
                $_.appRoleId -ceq $hostedServiceRole.id
            }
    )
    if ($hostedServiceAssignments.Count -gt 1) {
        throw 'Duplicate hosted-service API app-role assignments exist.'
    }
    if ($hostedServiceAssignments.Count -eq 0) {
        if (-not $Apply) {
            throw 'Hosted-service API app-role assignment is not configured.'
        }
        $hostedServiceAssignment = Invoke-GraphPost -Url $assignmentUrl -Body @{
            principalId = $HostedServicePrincipalObjectId
            resourceId = $apiServicePrincipal.id
            appRoleId = $hostedServiceRole.id
        }
    } else {
        $hostedServiceAssignment = $hostedServiceAssignments[0]
    }
}

$operatorAssignments = @()
if ($OperatorObjectId) {
    $operatorGuid = [guid]::Empty
    if (-not [guid]::TryParse($OperatorObjectId, [ref]$operatorGuid)) {
        throw 'OperatorObjectId must be one Entra object GUID.'
    }
    $operatorRoles = @(
        $configuredRoles |
            Where-Object { $_.value -cin @('Workflow.Approver', 'Acceptance.Operator') }
    )
    if ($operatorRoles.Count -ne 2) {
        throw 'The operator app roles are not configured exactly once.'
    }
    $assignedPayload = az rest `
        --method get `
        --url "https://graph.microsoft.com/v1.0/servicePrincipals/$($apiServicePrincipal.id)/appRoleAssignedTo" `
        --output json `
        --only-show-errors
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to inspect operator API app-role assignments.'
    }
    $assigned = @((($assignedPayload | ConvertFrom-Json).value))
    foreach ($role in $operatorRoles) {
        $matches = @(
            $assigned |
                Where-Object {
                    $_.principalId -ceq $OperatorObjectId -and
                    $_.appRoleId -ceq $role.id
                }
        )
        if ($matches.Count -gt 1) {
            throw "Duplicate operator app-role assignments exist for $($role.value)."
        }
        if ($matches.Count -eq 0) {
            if (-not $Apply) {
                throw "Operator app-role assignment is not configured for $($role.value)."
            }
            $matches = @(
                Invoke-GraphPost `
                    -Url "https://graph.microsoft.com/v1.0/servicePrincipals/$($apiServicePrincipal.id)/appRoleAssignedTo" `
                    -Body @{
                        principalId = $OperatorObjectId
                        resourceId = $apiServicePrincipal.id
                        appRoleId = $role.id
                    }
            )
        }
        $operatorAssignments += [ordered]@{
            role = $role.value
            assignmentId = $matches[0].id
        }
    }
}

[ordered]@{
    status = 'passed'
    mutationPerformed = [bool]$Apply
    tenantId = $TenantId
    apiClientId = $apiApplication.appId
    apiAppIdUri = $resolvedApiAppIdUri
    apiServicePrincipalObjectId = $apiServicePrincipal.id
    spaClientId = $spaApplication.appId
    preAuthorizedClientApplicationIds = $requiredClientIds
    redirectUris = $redirectUris
    delegatedScopes = @($scopeDefinitions.value)
    appRoles = @($roleDefinitions.value)
    hostedServiceAppRoleId = $hostedServiceRole.id
    hostedServiceRoleValue = $hostedServiceRole.value
    hostedServiceAssignmentId = $hostedServiceAssignment.id
    operatorObjectId = $OperatorObjectId
    operatorAssignments = $operatorAssignments
} | ConvertTo-Json -Depth 5
