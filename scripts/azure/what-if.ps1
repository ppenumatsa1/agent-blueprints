[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$Location,
    [Parameter(Mandatory)]
    [string]$ParameterFile,
    [string]$SubscriptionId = $env:AZURE_SUBSCRIPTION_ID,
    [string]$DeploymentName = 'agent-blueprints-foundry-preview'
)

$ErrorActionPreference = 'Stop'
$root = Resolve-Path "$PSScriptRoot\..\.."
$resolvedParameters = Resolve-Path $ParameterFile

if (-not $SubscriptionId) {
    throw 'SubscriptionId or AZURE_SUBSCRIPTION_ID is required.'
}
$activeSubscription = az account show --query id --output tsv --only-show-errors
if ($LASTEXITCODE -ne 0 -or $activeSubscription -cne $SubscriptionId) {
    throw 'Azure CLI active subscription does not match the requested what-if subscription.'
}

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
