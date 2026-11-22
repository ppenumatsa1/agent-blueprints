[CmdletBinding()]
param(
    [switch]$Apply,
    [switch]$SkipMigration,
    [Parameter(Mandatory)]
    [string]$OperatorIp
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\common.ps1"

if (-not $Apply) {
    throw 'Deployment is disabled by default. Re-run with -Apply after validation and approval.'
}

& "$PSScriptRoot\preflight.ps1" -FromAzdEnvironment

$values = Get-AzdEnvironmentValues
if ((Get-RequiredValue $values 'AZURE_APPLICATION_RUNTIME_READY') -cne 'true') {
    throw 'Application integration is not approved for Azure deployment.'
}

& "$PSScriptRoot\configure-entra.ps1" -Apply

$previousUserAgent = $env:AZURE_DEV_USER_AGENT
$previousTenantId = $env:VITE_ENTRA_TENANT_ID
$previousSpaClientId = $env:VITE_ENTRA_SPA_CLIENT_ID
$previousApiAppIdUri = $env:VITE_ENTRA_API_APP_ID_URI
try {
    $env:AZURE_DEV_USER_AGENT = 'microsoft_foundry_skill'
    azd provision --no-prompt
    if ($LASTEXITCODE -ne 0) { throw 'azd provision failed.' }

    $values = Get-AzdEnvironmentValues
    $webFqdn = Get-RequiredValue $values 'AZURE_WEB_FQDN'
    & "$PSScriptRoot\configure-entra.ps1" `
        -Apply `
        -FrontendRedirectUri "https://$webFqdn"

    & "$PSScriptRoot\configure-postgres.ps1" -Apply -OperatorIp $OperatorIp
    if (-not $SkipMigration) {
        & "$PSScriptRoot\migrate.ps1" -Apply -OperatorIp $OperatorIp
    }

    $values = Get-AzdEnvironmentValues
    $env:VITE_ENTRA_TENANT_ID = Get-RequiredValue $values 'AZURE_TENANT_ID'
    $env:VITE_ENTRA_SPA_CLIENT_ID = Get-RequiredValue $values 'AZURE_SPA_ENTRA_CLIENT_ID'
    $env:VITE_ENTRA_API_APP_ID_URI = Get-RequiredValue $values 'AZURE_API_ENTRA_APP_ID_URI'
    azd deploy --no-prompt
    if ($LASTEXITCODE -ne 0) { throw 'azd deploy failed.' }
}
finally {
    $env:AZURE_DEV_USER_AGENT = $previousUserAgent
    $env:VITE_ENTRA_TENANT_ID = $previousTenantId
    $env:VITE_ENTRA_SPA_CLIENT_ID = $previousSpaClientId
    $env:VITE_ENTRA_API_APP_ID_URI = $previousApiAppIdUri
}

python "$PSScriptRoot\health-check.py"
if ($LASTEXITCODE -ne 0) { throw 'Deployment health verification failed.' }
