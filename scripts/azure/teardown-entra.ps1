[CmdletBinding()]
param(
    [switch]$Apply,
    [ValidateSet('AzureCli', 'Azd')]
    [string]$DeploymentMode = 'AzureCli',
    [string]$ValuesFile,
    [Parameter(Mandatory)]
    [string]$ConfirmApiDisplayName,
    [Parameter(Mandatory)]
    [string]$ConfirmSpaDisplayName,
    [string]$ApiDisplayName = 'agent-blueprints-order-resolution-api',
    [string]$SpaDisplayName = 'agent-blueprints-order-resolution-spa'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\common.ps1"

if (-not $Apply) {
    throw 'DESTRUCTIVE: Entra teardown is disabled by default. Re-run with -Apply and both exact display names.'
}
if (
    $ConfirmApiDisplayName -cne $ApiDisplayName -or
    $ConfirmSpaDisplayName -cne $SpaDisplayName
) {
    throw 'DESTRUCTIVE: Entra application confirmation does not match.'
}

$values = Get-DeploymentValues -DeploymentMode $DeploymentMode -ValuesFile $ValuesFile
Invoke-DeploymentPreflight -DeploymentMode $DeploymentMode -Values $values
$expectedApiClientId = Get-RequiredValue $values 'AZURE_API_ENTRA_CLIENT_ID'
$expectedSpaClientId = Get-RequiredValue $values 'AZURE_SPA_ENTRA_CLIENT_ID'

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
    if ($matches.Count -ne 1) {
        throw "Expected exactly one Entra application named $DisplayName."
    }
    return $matches[0]
}

$apiApplication = Get-ExactApplication -DisplayName $ApiDisplayName
$spaApplication = Get-ExactApplication -DisplayName $SpaDisplayName
if (
    $apiApplication.appId -cne $expectedApiClientId -or
    $spaApplication.appId -cne $expectedSpaClientId
) {
    throw 'DESTRUCTIVE: Entra application IDs do not match the selected deployment values.'
}

az ad app delete --id $spaApplication.appId --only-show-errors
if ($LASTEXITCODE -ne 0) {
    throw "Unable to delete Entra application $SpaDisplayName."
}
az ad app delete --id $apiApplication.appId --only-show-errors
if ($LASTEXITCODE -ne 0) {
    throw "Unable to delete Entra application $ApiDisplayName."
}
