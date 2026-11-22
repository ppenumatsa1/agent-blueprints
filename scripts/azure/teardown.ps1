[CmdletBinding()]
param(
    [switch]$Apply,
    [Parameter(Mandatory)]
    [string]$ConfirmEnvironmentName
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\common.ps1"

if (-not $Apply) {
    throw 'DESTRUCTIVE: teardown is disabled by default. Re-run with -Apply and the exact environment name.'
}

& "$PSScriptRoot\preflight.ps1" -FromAzdEnvironment
$values = Get-AzdEnvironmentValues
$environmentName = Get-RequiredValue $values 'AZURE_ENV_NAME'
$subscriptionId = Get-RequiredValue $values 'AZURE_SUBSCRIPTION_ID'
$resourceGroup = Get-RequiredValue $values 'AZURE_RESOURCE_GROUP'

if ($ConfirmEnvironmentName -cne $environmentName) {
    throw 'DESTRUCTIVE: confirmation does not match the selected azd environment.'
}

$tag = az group show `
    --subscription $subscriptionId `
    --name $resourceGroup `
    --query "tags.\"azd-env-name\"" `
    --output tsv
if ($LASTEXITCODE -ne 0 -or $tag -cne $environmentName) {
    throw 'DESTRUCTIVE: the resource group is not tagged for the selected azd environment.'
}

$previousUserAgent = $env:AZURE_DEV_USER_AGENT
try {
    $env:AZURE_DEV_USER_AGENT = 'microsoft_foundry_skill'
    azd down --environment $environmentName --purge --force --no-prompt
    if ($LASTEXITCODE -ne 0) { throw 'azd teardown failed.' }
}
finally {
    $env:AZURE_DEV_USER_AGENT = $previousUserAgent
}
