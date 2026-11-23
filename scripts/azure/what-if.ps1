[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Location,
    [Parameter(Mandatory)]
    [string]$ParameterFile,
    [string]$SubscriptionId = $env:AZURE_SUBSCRIPTION_ID,
    [string]$TenantId = $env:AZURE_TENANT_ID,
    [string]$ExpectedUser = $env:AZURE_EXPECTED_USER,
    [string]$DeploymentName = 'agent-blueprints-foundry-preview'
)

$ErrorActionPreference = 'Stop'
$root = Resolve-Path "$PSScriptRoot\..\.."
$resolvedParameters = Resolve-Path $ParameterFile

& "$PSScriptRoot\preflight.ps1" `
    -DeploymentMode AzureCli `
    -SubscriptionId $SubscriptionId `
    -TenantId $TenantId `
    -ExpectedUser $ExpectedUser `
    -Location $Location

Push-Location $root
try {
    az deployment sub what-if `
        --subscription $SubscriptionId `
        --name $DeploymentName `
        --location $Location `
        --template-file infra\main.bicep `
        --parameters $resolvedParameters `
        --validation-level ProviderNoRbac `
        --no-pretty-print
    if ($LASTEXITCODE -ne 0) { throw 'Subscription what-if failed.' }
}
finally {
    Pop-Location
}
